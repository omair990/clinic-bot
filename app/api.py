"""JSON API for the React admin console (served under /api).

Mirrors the data and actions of the legacy Jinja admin, but returns JSON and uses JSON
401/403 instead of HTML redirects. Auth is the SAME cookie session as before (set at
/api/login, read from request.session) — the SPA is served same-origin, so the session
cookie just works. Tenant scoping mirrors the Jinja admin: a clinic login is locked to its
own tenant; the super-admin sees everything, or one clinic via the `clinic` query param.
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app import db
from app import insights as insights_mod
from app import no_show as no_show_mod
from app.auth import verify_password
from app.config import (
    ADMIN_PASSWORD,
    NO_SHOW_AUTO_SEND,
    NO_SHOW_PREDICTOR,
    NOTIFY_ON_STATUS_CHANGE,
    TZ,
)
from app.notifications import notify_appointment_status
from app.tenancy import current_period

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

APPOINTMENT_STATUSES = {"confirmed", "cancelled", "completed", "no_show"}


# --------------------------------------------------------------------------- auth helpers
def _principal(request: Request) -> dict | None:
    role = request.session.get("role")
    if not role:
        return None
    return {"role": role, "tenant_id": request.session.get("tenant_id"),
            "tenant_name": request.session.get("tenant_name")}


def _require(request: Request) -> dict:
    p = _principal(request)
    if not p:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return p


def _require_super(request: Request) -> dict:
    p = _require(request)
    if p["role"] != "super":
        raise HTTPException(status_code=403, detail="Super-admin only")
    return p


def _view_scope(request: Request) -> int | None:
    """Clinic login → own tenant; super → all, or one via ?clinic=<id>."""
    p = _require(request)
    if p["role"] == "clinic":
        return p["tenant_id"]
    raw = (request.query_params.get("clinic") or "").strip()
    return int(raw) if raw.isdigit() else None


def _tenant_names() -> dict:
    try:
        return {t["id"]: t["name"] for t in db.list_tenants(current_period(str(TZ)))}
    except Exception:  # noqa: BLE001
        return {}


def _filter_meta(request: Request) -> dict:
    """Clinic-filter metadata the SPA needs to render the picker + Clinic column."""
    if _require(request)["role"] != "super":
        return {"is_super": False, "clinics": [], "selected_clinic": None, "tenant_names": {}}
    names = _tenant_names()
    return {
        "is_super": True,
        "clinics": [{"id": i, "name": n} for i, n in names.items()],
        "selected_clinic": _view_scope(request),
        "tenant_names": {str(k): v for k, v in names.items()},
    }


def _month_start() -> datetime:
    now = datetime.now(TZ)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


# --------------------------------------------------------------------------- auth routes
@router.post("/login")
async def login(request: Request, body: dict = Body(...)):
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not username and password == ADMIN_PASSWORD:
        request.session.clear()
        request.session["role"] = "super"
        return {"role": "super", "tenant_id": None, "tenant_name": None}
    if username:
        t = db.get_tenant_by_username(username)
        if t and verify_password(password, t.get("staff_password_hash")):
            request.session.clear()
            request.session.update(
                {"role": "clinic", "tenant_id": t["id"], "tenant_name": t["name"]})
            return {"role": "clinic", "tenant_id": t["id"], "tenant_name": t["name"]}
    raise HTTPException(status_code=401, detail="Invalid credentials")


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me")
async def me(request: Request):
    return _require(request)


# --------------------------------------------------------------------------- dashboards
@router.get("/overview")
async def overview(request: Request):
    """Super-admin per-clinic overview (one row per clinic)."""
    _require_super(request)
    return {"clinics": db.clinic_overview(current_period(str(TZ)), _month_start())}


@router.get("/dashboard")
async def dashboard(request: Request):
    """A single clinic's own dashboard stats."""
    scope = _view_scope(request)
    return {"stats": db.stats(scope),
            "no_shows_month": db.no_show_count_since(_month_start(), scope)}


@router.get("/clinics")
async def clinics(request: Request):
    """Tenant id/name list for filters (super only; clinic gets just its own)."""
    p = _require(request)
    if p["role"] == "clinic":
        return [{"id": p["tenant_id"], "name": p["tenant_name"]}]
    return [{"id": i, "name": n} for i, n in _tenant_names().items()]


# --------------------------------------------------------------------------- conversations
@router.get("/conversations")
async def conversations(request: Request):
    return {"rows": db.list_conversations(tenant_id=_view_scope(request)),
            **_filter_meta(request)}


@router.get("/conversations/{wa_user}")
async def conversation(request: Request, wa_user: str):
    scope = _view_scope(request)
    tid = scope if scope is not None else db.tenant_id_for_user(wa_user)
    analysis = None
    try:
        analysis = analysis_for(wa_user, tid)
    except Exception:  # noqa: BLE001
        pass
    return {"wa_user": wa_user,
            "messages": db.conversation_thread(wa_user, tenant_id=scope),
            "analysis": analysis}


def analysis_for(wa_user: str, tenant_id: int | None):
    from app import analysis as analysis_mod
    if not tenant_id:
        return None
    return analysis_mod.get_or_build(tenant_id, wa_user)


@router.post("/conversations/{wa_user}/analysis/refresh")
async def refresh_analysis(request: Request, wa_user: str):
    from app import analysis as analysis_mod
    scope = _view_scope(request)
    tid = scope if scope is not None else db.tenant_id_for_user(wa_user)
    if not tid:
        raise HTTPException(404, "Unknown conversation")
    return {"analysis": analysis_mod.get_or_build(tid, wa_user, force=True)}


# --------------------------------------------------------------------------- appointments
@router.get("/appointments")
async def appointments(request: Request, status: str | None = Query(None)):
    return {"rows": db.list_appointments(status, tenant_id=_view_scope(request)),
            "filter_status": status, **_filter_meta(request)}


@router.post("/appointments/{appointment_id}/status")
async def set_appt_status(request: Request, appointment_id: int, body: dict = Body(...)):
    p = _require(request)
    scope = p["tenant_id"] if p["role"] == "clinic" else None
    status = (body.get("status") or "").strip()
    if status not in APPOINTMENT_STATUSES:
        raise HTTPException(400, "bad status")
    appt = db.get_appointment_by_id(appointment_id)
    prior = appt["status"] if appt else None
    if scope is None:
        db.admin_set_appointment_status(appointment_id, status)
    else:
        db.set_appointment_status(scope, appointment_id, status)
    notify = (NOTIFY_ON_STATUS_CHANGE and appt and status != prior
              and status in ("cancelled", "completed")
              and (scope is None or appt["tenant_id"] == scope))
    if notify:
        try:
            tenant = db.get_tenant(appt["tenant_id"])
            if tenant:
                await notify_appointment_status(appt, status, tenant)
        except Exception as e:  # noqa: BLE001
            log.warning("status-change notify failed for appt %s: %s", appointment_id, str(e)[:160])
    return {"ok": True}


# --------------------------------------------------------------------------- no-shows
@router.get("/no-shows")
async def no_shows(request: Request):
    scope = _view_scope(request)
    since = _month_start()
    return {
        "rows": db.list_no_show_followups(tenant_id=scope),
        "month_count": db.no_show_count_since(since, scope),
        "reasons": db.no_show_reason_breakdown(since, scope),
        "risk": db.risk_band_counts(scope),
        "predictor_on": NO_SHOW_PREDICTOR,
        "auto_send": NO_SHOW_AUTO_SEND,
        "reason_labels": no_show_mod.REASON_LABELS,
        **_filter_meta(request),
    }


@router.post("/no-shows/{followup_id}/action")
async def no_show_action(request: Request, followup_id: int, body: dict = Body(...)):
    p = _require(request)
    scope = p["tenant_id"] if p["role"] == "clinic" else None
    action = (body.get("action") or "").strip()
    fu = db.get_followup(followup_id, tenant_id=scope)
    if not fu:
        raise HTTPException(404, "Follow-up not found")
    if action in ("send", "resend"):
        tenant = db.get_tenant(fu["tenant_id"])
        if tenant:
            creds = {"phone_number_id": tenant.get("wa_phone_number_id"),
                     "access_token": tenant.get("wa_access_token")}
            try:
                await no_show_mod.send_no_show_notification(
                    to=fu["wa_user"], service=fu.get("service"), doctor=fu.get("doctor"),
                    creds=creds, tenant_id=fu["tenant_id"], followup_id=fu["id"],
                    tenant=tenant, advance=(fu["stage"] == "detected"))
            except Exception as e:  # noqa: BLE001
                log.warning("manual no-show send failed: %s", str(e)[:160])
    elif action == "resolve":
        db.set_followup_stage(followup_id, "resolved", stamp="resolved_at")
    elif action == "inactive":
        db.set_followup_stage(followup_id, "inactive", stamp="resolved_at")
    return {"ok": True}


# --------------------------------------------------------------------------- reviews
@router.get("/reviews")
async def reviews(request: Request):
    scope = _view_scope(request)
    return {"rows": db.list_reviews(tenant_id=scope), "stats": db.review_stats(scope),
            **_filter_meta(request)}


# --------------------------------------------------------------------------- insights
@router.get("/insights")
async def insights(request: Request, period: str = Query("day")):
    scope = _view_scope(request)
    report = await _to_thread(insights_mod.report, scope, period, str(TZ))
    return {"report": report, "period": period, **_filter_meta(request)}


# --------------------------------------------------------------------------- usage (clinic)
@router.get("/usage")
async def usage(request: Request):
    p = _require(request)
    if p["role"] != "clinic":
        raise HTTPException(400, "Super-admins use /api/plans")
    period = current_period(str(TZ))
    return {"period": period, "usage": db.tenant_usage_row(p["tenant_id"], period)}


# --------------------------------------------------------------------------- plans / tenants
@router.get("/plans")
async def plans(request: Request):
    _require_super(request)
    period = current_period(str(TZ))
    return {"plans": db.list_plans(), "tenants": db.list_tenants(period), "period": period}


@router.post("/plans")
async def save_plan(request: Request, body: dict = Body(...)):
    _require_super(request)

    def _int(v):
        v = str(v).strip() if v is not None else ""
        return int(v) if v else None
    db.upsert_plan(
        (body.get("name") or "").strip(),
        _int(body.get("monthly_text_quota")),
        bool(body.get("voice_enabled")),
        _int(body.get("monthly_voice_quota")),
        bool(body.get("is_trial")),
        _int(body.get("trial_days")),
        _int(body.get("price_sar")),
    )
    return {"ok": True}


@router.post("/tenants/{tenant_id}/plan")
async def set_plan(request: Request, tenant_id: int, body: dict = Body(...)):
    _require_super(request)
    db.set_tenant_plan(tenant_id, int(body["plan_id"]))
    return {"ok": True}


@router.post("/tenants/{tenant_id}/status")
async def set_status(request: Request, tenant_id: int, body: dict = Body(...)):
    _require_super(request)
    db.set_tenant_status(tenant_id, (body.get("status") or "").strip())
    return {"ok": True}


# --------------------------------------------------------------------------- issues (super)
@router.get("/logs")
async def logs(request: Request, show: str = Query("open")):
    _require_super(request)
    scope = _view_scope(request)
    resolved = {"open": False, "resolved": True}.get(show, None)
    return {"events": db.list_events(resolved=resolved, tenant_id=scope),
            "open_count": db.unresolved_event_count(scope), "show": show,
            **_filter_meta(request)}


@router.post("/logs/{event_id}/resolve")
async def resolve_log(request: Request, event_id: int):
    _require_super(request)
    db.resolve_event(event_id, tenant_id=None)
    return {"ok": True}


# --------------------------------------------------------------------------- util
async def _to_thread(fn, *args):
    import asyncio
    return await asyncio.to_thread(fn, *args)
