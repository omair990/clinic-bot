"""JSON API for the React admin console (served under /api).

Mirrors the data and actions of the legacy Jinja admin, but returns JSON and uses JSON
401/403 instead of HTML redirects. Auth is the SAME cookie session as before (set at
/api/login, read from request.session) — the SPA is served same-origin, so the session
cookie just works. Tenant scoping mirrors the Jinja admin: a clinic login is locked to its
own tenant; the super-admin sees everything, or one clinic via the `clinic` query param.
"""
import json
import logging
import secrets
from datetime import datetime

import psycopg
from fastapi import APIRouter, Body, HTTPException, Query, Request

from app import clinic_schema as cs
from app import connectors as connectors_mod
from app import db
from app import insights as insights_mod
from app import no_show as no_show_mod
from app.auth import hash_password, verify_password
from app.events import publish
from app.config import (
    ADMIN_ACCOUNTS,
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
        return {"role": "super", "tenant_id": None, "tenant_name": None, "timezone": str(TZ)}
    # Named platform-admin accounts (ADMIN_ACCOUNTS) — same super access, shareable login.
    if username and username in ADMIN_ACCOUNTS and secrets.compare_digest(ADMIN_ACCOUNTS[username], password):
        request.session.clear()
        request.session.update({"role": "super", "tenant_name": username})
        return {"role": "super", "tenant_id": None, "tenant_name": username, "timezone": str(TZ)}
    if username:
        t = db.get_tenant_by_username(username)
        if t and verify_password(password, t.get("staff_password_hash")):
            request.session.clear()
            request.session.update(
                {"role": "clinic", "tenant_id": t["id"], "tenant_name": t["name"]})
            return {"role": "clinic", "tenant_id": t["id"], "tenant_name": t["name"],
                    "timezone": t.get("timezone") or str(TZ)}
    raise HTTPException(status_code=401, detail="Invalid credentials")


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me")
async def me(request: Request):
    p = _require(request)
    # Timezone the console should render all times in: the clinic's own zone for a clinic
    # login, the platform default for the super-admin (who sees many clinics at once).
    tz = str(TZ)
    if p["role"] == "clinic" and p.get("tenant_id"):
        t = db.get_tenant(p["tenant_id"])
        if t and t.get("timezone"):
            tz = t["timezone"]
    return {**p, "timezone": tz}


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
    try:
        from app.wa_client import auth_failing
        wa_failing = auth_failing()
    except Exception:  # noqa: BLE001
        wa_failing = False
    return {"stats": db.stats(scope),
            "no_shows_month": db.no_show_count_since(_month_start(), scope),
            "wa_send_failing": wa_failing}


@router.get("/clinics/{tenant_id}")
async def clinic_detail(request: Request, tenant_id: int):
    """Single-clinic profile: at-a-glance metrics, usage, trend, recent activity."""
    _require_super(request)
    period = current_period(str(TZ))
    ov = next((c for c in db.clinic_overview(period, _month_start()) if c["id"] == tenant_id), None)
    if not ov:
        raise HTTPException(404, "Clinic not found")
    return {
        "clinic": ov,
        "stats": db.stats(tenant_id),
        "trends": db.daily_message_counts(14, tenant_id),
        "review_stats": db.review_stats(tenant_id),
        "recent_appointments": db.list_appointments(None, tenant_id=tenant_id)[:8],
        "recent_reviews": db.list_reviews(tenant_id=tenant_id)[:6],
    }


@router.get("/trends")
async def trends(request: Request):
    """Real daily inbound-message series (last 14 days) for dashboard sparklines."""
    return {"daily_messages": db.daily_message_counts(14, _view_scope(request))}


# --------------------------------------------------------------------------- real-time
@router.get("/stream")
async def stream(request: Request):
    """Server-Sent Events feed: live messages, typing, and staff notifications.

    Scoped like the rest of the console — a clinic login only receives its own tenant's
    events; the super-admin receives everything. Keepalive comments every 15s keep the
    connection (and any proxy) from idling out."""
    import asyncio

    from fastapi.responses import StreamingResponse
    from app import events

    p = _require(request)
    scope = p["tenant_id"] if p["role"] == "clinic" else None

    async def gen():
        q = events.subscribe()
        try:
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                tid = ev.get("tenant_id")
                if scope is not None and tid is not None and tid != scope:
                    continue  # not this clinic's event
                yield f"data: {json.dumps(ev, default=str)}\n\n"
        finally:
            events.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # don't let nginx/proxies buffer the stream
    })


@router.get("/notifications")
async def notifications(request: Request):
    """Recent staff notifications (newest first) + the durable unread count, for the bell.

    Both are DB-backed (the `notifications` table + the per-viewer `notification_seen`
    marker), so history and the unread badge survive a page refresh and a server restart."""
    p = _require(request)
    scope = p["tenant_id"] if p["role"] == "clinic" else None
    return {"notifications": db.list_notifications(scope),
            "unread": db.notifications_unread(scope)}


@router.post("/notifications/seen")
async def notifications_seen(request: Request):
    """Mark all currently-visible notifications as seen for this viewer (badge → 0)."""
    p = _require(request)
    scope = p["tenant_id"] if p["role"] == "clinic" else None
    db.mark_notifications_seen(scope)
    return {"ok": True, "unread": 0}


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


@router.get("/patients/{wa_user}")
async def patient(request: Request, wa_user: str):
    """360° patient profile: profile + conversation + appointments + reviews + no-shows."""
    scope = _view_scope(request)
    tid = scope if scope is not None else db.tenant_id_for_user(wa_user)
    if tid is None:
        raise HTTPException(404, "Unknown patient")
    analysis = None
    try:
        from app import analysis as analysis_mod
        analysis = analysis_mod.get_or_build(tid, wa_user)
    except Exception:  # noqa: BLE001
        pass
    return {
        "wa_user": wa_user,
        "tenant_id": tid,
        "clinic": _tenant_names().get(tid),
        "name": db.get_patient_name(tid, wa_user),
        "message_count": db.message_count(tid, wa_user),
        "analysis": analysis,
        "messages": db.conversation_thread(wa_user, tenant_id=tid),
        "appointments": db.appointments_for_user(tid, wa_user),
        "reviews": db.reviews_for_user(tid, wa_user),
        "no_shows": db.no_shows_for_user(tid, wa_user),
    }


@router.post("/conversations/{wa_user}/message")
async def add_message(request: Request, wa_user: str, body: dict = Body(...)):
    """Manually add a chat message to a patient's thread (admin-authored, record-only).

    This does NOT send anything over WhatsApp — it only inserts the row so the message
    appears in the thread + live feed. Lets staff backfill or correct conversation history.
    """
    _require(request)
    direction = (body.get("direction") or "").strip()
    if direction not in ("in", "out"):
        raise HTTPException(400, "direction must be 'in' or 'out'")
    message = (body.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "message is required")
    # Resolve the tenant exactly like the read endpoints: a clinic login is locked to its own
    # tenant; super-admin uses ?clinic=<id>, falling back to the patient's existing tenant.
    scope = _view_scope(request)
    tid = scope if scope is not None else db.tenant_id_for_user(wa_user)
    if tid is None:
        raise HTTPException(404, "Unknown patient")
    mid = db.log_message(tid, wa_user, direction, message, source="text")
    # Mirror the live-feed payload webhook.py publishes so open consoles merge it instantly.
    publish("message", {"wa_user": wa_user, "direction": direction, "text": message,
                        "tenant_id": tid, "source": "text"})
    log.info("admin added %s message for %s (tenant %s, id %s)", direction, wa_user, tid, mid)
    return {"ok": True, "id": mid}


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
async def insights(request: Request, period: str = Query("day"), lang: str = Query("en")):
    scope = _view_scope(request)
    lang = "ar" if lang == "ar" else "en"
    report = await _to_thread(insights_mod.report, scope, period, str(TZ), None, lang)
    return {"report": report, "period": period, **_filter_meta(request)}


# --------------------------------------------------------------------------- usage (clinic)
@router.get("/usage")
async def usage(request: Request):
    p = _require(request)
    if p["role"] != "clinic":
        raise HTTPException(400, "Super-admins use /api/plans")
    period = current_period(str(TZ))
    return {"period": period, "usage": db.tenant_usage_row(p["tenant_id"], period)}


# --------------------------------------------------------------------------- cost calculator (super)
# Public Anthropic list prices (USD per 1M tokens) per Claude tier — used ONLY as editable
# defaults the owner tunes in the calculator. Not authoritative; the UI lets them override.
_CLAUDE_PRICES = {
    "opus": {"input": 15.0, "output": 75.0},
    "sonnet": {"input": 3.0, "output": 15.0},
    "haiku": {"input": 1.0, "output": 5.0},
}


def _claude_price_default(model: str) -> dict:
    m = (model or "").lower()
    for tier, px in _CLAUDE_PRICES.items():
        if tier in m:
            return px
    return _CLAUDE_PRICES["sonnet"]


@router.get("/cost-calculator")
async def cost_calculator(request: Request):
    """Super-admin cost calculator: real message volume for the period plus sensible default
    unit rates, so the owner can estimate Claude, WhatsApp and hosting cost in SAR and price
    plans. Rates are returned as defaults only — the UI keeps the owner's edits client-side."""
    _require_super(request)
    from app.config import CLAUDE_MODEL
    period = current_period(str(TZ))
    tenants = db.list_tenants(period)
    # Exact, real usage this period straight from the conversation log (per tenant).
    try:
        breakdown = db.usage_breakdown(_month_start())
    except Exception:  # noqa: BLE001 — usage detail is best-effort; never 500 the calculator
        log.warning("usage_breakdown failed", exc_info=True)
        breakdown = {}
    try:
        tokens = db.usage_tokens(period)              # real Claude tokens, per tenant
    except Exception:  # noqa: BLE001
        log.warning("usage_tokens failed", exc_info=True)
        tokens = {}
    clinics = []
    for t in tenants:
        b = breakdown.get(t["id"], {})
        tk = tokens.get(t["id"], {})
        clinics.append({
            "id": t["id"], "name": t["name"], "slug": t.get("slug"),
            "inbound": int(b.get("inbound") or 0),
            "voice": int(b.get("voice_in") or 0),
            "replies": int(b.get("replies") or 0),
            "reminders": int(b.get("reminders") or 0),
            "input_tokens": int(tk.get("input_tokens") or 0),
            "output_tokens": int(tk.get("output_tokens") or 0),
        })
    inbound = sum(c["inbound"] for c in clinics)
    voice = sum(c["voice"] for c in clinics)
    replies = sum(c["replies"] for c in clinics)
    reminders = sum(c["reminders"] for c in clinics)
    input_tokens = sum(c["input_tokens"] for c in clinics)
    output_tokens = sum(c["output_tokens"] for c in clinics)
    px = _claude_price_default(CLAUDE_MODEL)
    # Ratios observed this period seed the estimator so "1000 messages" auto-scales replies
    # and reminders realistically; fall back to sane priors when there's no traffic yet.
    reminders_per = round(reminders / inbound, 3) if inbound else 0.1
    replies_per = round(replies / inbound, 2) if inbound else 1.0
    # Seed avg tokens/message from REAL captured usage once we have some; until then (capture
    # only began when the token columns shipped), fall back to priors. The priors are sized
    # to a measured turn (~9.7k input on a full tool-using booking, where cache reads count as
    # input + the system prompt re-sends each round-trip), so the estimate doesn't understate.
    tokens_captured = bool(input_tokens or output_tokens)
    avg_in = round(input_tokens / inbound) if (inbound and input_tokens) else 6000
    avg_out = round(output_tokens / inbound) if (inbound and output_tokens) else 300
    return {
        "period": period,
        "model": CLAUDE_MODEL,
        "totals": {"inbound": inbound, "voice": voice, "replies": replies,
                   "reminders": reminders, "messages": inbound, "clinics": len(clinics),
                   "input_tokens": input_tokens, "output_tokens": output_tokens,
                   "tokens_captured": tokens_captured},
        "clinics": clinics,
        "defaults": {
            "usd_to_sar": 3.75,                       # SAR is pegged to USD at ~3.75
            "claude_input_usd_per_mtok": px["input"],
            "claude_output_usd_per_mtok": px["output"],
            "avg_input_tokens_per_inquiry": avg_in,   # real average once captured, else a prior
            "avg_output_tokens_per_inquiry": avg_out,
            "whatsapp_sar_per_conversation": 0.20,    # service conversation (region/category dependent)
            "messages_per_conversation": 4,           # inbound msgs that fall in one 24h WA window
            "whatsapp_sar_per_reminder": 0.20,        # proactive (utility) template message
            "reminders_per_inquiry": reminders_per,   # seeded from this period's real ratio
            "replies_per_inquiry": replies_per,
            "voice_sar_per_message": 0.15,            # transcription + TTS surcharge per voice note
            "railway_usd_per_month": 20.0,            # flat hosting; spread across all inquiries
        },
    }


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


# --------------------------------------------------------------------------- tenants
def _parse_clinic_data(raw: str):
    """('normalized dict' | None, warnings). Raises HTTPException(400) on JSON/schema errors."""
    raw = (raw or "").strip()
    if not raw:
        return None, []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Invalid JSON: {e}")
    norm, errors, warnings = cs.validate_and_normalize(data)
    if errors:
        raise HTTPException(400, "Clinic data invalid — " + "; ".join(errors))
    return norm, warnings


@router.get("/tenants/{tenant_id}")
async def get_tenant(request: Request, tenant_id: int):
    _require_super(request)
    t = db.get_tenant(tenant_id)
    if not t:
        raise HTTPException(404, "Tenant not found")
    data = t.get("clinic_data") or {}
    return {
        "id": t["id"], "name": t.get("name"), "slug": t.get("slug"),
        "wa_phone_number_id": t.get("wa_phone_number_id") or "",
        "timezone": t.get("timezone") or "Asia/Riyadh",
        "staff_username": t.get("staff_username") or "",
        "has_wa_access_token": bool(t.get("wa_access_token")),
        # Structured (normalized) object for the guided editor — sections always present so
        # the editor renders clean empty tabs for a new clinic.
        "clinic_data_obj": {**cs.blank_template(), **cs.normalize(data)},
        "clinic_data": json.dumps(data, indent=2, ensure_ascii=False),
        "connector_type": (data.get("connector") or {}).get("type", "native"),
        "is_default": tenant_id == 1 or t.get("slug") == "default",
    }


@router.get("/weekdays")
async def weekdays(request: Request):
    _require(request)
    return {"days": cs.DAYS}


@router.post("/tenants")
async def create_tenant(request: Request, body: dict = Body(...)):
    _require_super(request)
    uname = (body.get("staff_username") or "").strip() or None
    if uname and db.staff_username_taken(uname):
        raise HTTPException(409, f'Staff username "{uname}" is already in use.')
    parsed, _w = _parse_clinic_data(body.get("clinic_data") or "")
    try:
        tid = db.create_tenant(
            (body.get("name") or "").strip(), (body.get("slug") or "").strip(),
            (body.get("wa_phone_number_id") or "").strip() or None,
            int(body["plan_id"]), (body.get("timezone") or "Asia/Riyadh").strip() or "Asia/Riyadh",
            (body.get("wa_access_token") or "").strip() or None, parsed)
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, "Slug, WhatsApp number, or staff username already in use.")
    if uname:
        db.set_tenant_credentials(tid, uname, hash_password(body.get("staff_password") or "") if body.get("staff_password") else None)
    return {"id": tid}


@router.post("/tenants/{tenant_id}/edit")
async def edit_tenant(request: Request, tenant_id: int, body: dict = Body(...)):
    _require_super(request)
    if not db.get_tenant(tenant_id):
        raise HTTPException(404, "Tenant not found")
    uname = (body.get("staff_username") or "").strip() or None
    parsed, warnings = _parse_clinic_data(body.get("clinic_data") or "")
    if uname and db.staff_username_taken(uname, exclude_tenant_id=tenant_id):
        raise HTTPException(409, f'Staff username "{uname}" is already in use.')
    db.update_tenant_config(
        tenant_id, name=(body.get("name") or "").strip(),
        wa_phone_number_id=(body.get("wa_phone_number_id") or "").strip() or None,
        wa_access_token=(body.get("wa_access_token") or "").strip() or None,
        timezone=(body.get("timezone") or "Asia/Riyadh").strip() or "Asia/Riyadh",
        clinic_data=parsed)
    pw = body.get("staff_password") or ""
    try:
        db.set_tenant_credentials(tenant_id, uname, hash_password(pw) if pw.strip() else None)
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, f'Staff username "{uname}" is already in use.')
    return {"ok": True, "warnings": warnings}


@router.post("/tenants/{tenant_id}/delete")
async def delete_tenant(request: Request, tenant_id: int, body: dict = Body(...)):
    _require_super(request)
    t = db.get_tenant(tenant_id)
    if not t:
        raise HTTPException(404, "Tenant not found")
    if tenant_id == 1 or t.get("slug") == "default":
        raise HTTPException(403, "The default tenant cannot be deleted.")
    if (body.get("confirm_slug") or "").strip() != t.get("slug"):
        raise HTTPException(400, f'Type the slug "{t.get("slug")}" to confirm deletion.')
    cleared = db.delete_tenant(tenant_id)
    log.warning("Tenant %s (%s) hard-deleted via API; cleared %s table(s)", tenant_id, t.get("slug"), cleared)
    return {"ok": True}


# --------------------------------------------------------------------------- connector
_SECRET_FIELDS = ("api_key", "refresh_token", "token", "value", "client_secret", "webhook_secret")


def _redact(cfg: dict) -> dict:
    """Mask secret values (top-level + nested auth) but report which are set."""
    out = json.loads(json.dumps(cfg or {}))
    secrets_set = []
    for d, prefix in ((out, ""), (out.get("auth") or {}, "auth.")):
        for f in _SECRET_FIELDS:
            if d.get(f):
                secrets_set.append(prefix + f)
                d[f] = ""
    return {"config": out, "secrets_set": secrets_set}


def _merge_secrets(submitted: dict, existing: dict) -> dict:
    """Carry over existing secrets where the submitted value is blank (blank = keep)."""
    out = json.loads(json.dumps(submitted or {}))
    for d, e in ((out, existing or {}), (out.get("auth") or {}, (existing or {}).get("auth") or {})):
        for f in _SECRET_FIELDS:
            if f in d and not d.get(f) and e.get(f):
                d[f] = e[f]
    return out


def _validate_connector(cfg: dict) -> str | None:
    """Per-type required-field validation of a (secrets-merged) connector config. Returns an
    error message, or None if valid. Mirrors the old form builder's rules."""
    t = cfg.get("type")

    def missing(field: str) -> bool:
        return not str(cfg.get(field) or "").strip()

    def bad_map(field: str, label: str) -> str | None:
        v = cfg.get(field)
        return f"{label} must be a JSON object." if (v is not None and not isinstance(v, dict)) else None

    if t == "google_calendar":
        if missing("refresh_token"):
            return "Refresh token is required for Google Calendar."
        return bad_map("calendars", "Calendars (doctor → calendarId)")
    if t == "cliniko":
        if missing("api_key"):
            return "API key is required for Cliniko."
        if missing("business_id"):
            return "Business id is required for Cliniko."
        return bad_map("practitioners", "Practitioners") or bad_map("appointment_types", "Appointment types")
    if t == "custom_erp":
        return "Base URL is required for Custom ERP." if missing("base_url") else None
    if t == "fhir":
        if missing("base_url"):
            return "Base URL is required for FHIR."
        return bad_map("schedules", "Schedules") or bad_map("practitioners", "Practitioners")
    if t in (None, "native"):
        return None
    return f"Unknown connector type: {t}"


@router.get("/tenants/{tenant_id}/connector")
async def get_connector(request: Request, tenant_id: int):
    _require_super(request)
    t = db.get_tenant(tenant_id)
    if not t:
        raise HTTPException(404, "Tenant not found")
    conn = (t.get("clinic_data") or {}).get("connector") or {}
    return {"tenant_id": tenant_id, "name": t.get("name"), **_redact(conn)}


@router.post("/tenants/{tenant_id}/connector")
async def save_connector(request: Request, tenant_id: int, body: dict = Body(...)):
    _require_super(request)
    t = db.get_tenant(tenant_id)
    if not t:
        raise HTTPException(404, "Tenant not found")
    cfg = body.get("config")
    if cfg and (cfg.get("type") or "native") != "native":
        cfg = _merge_secrets(cfg, (t.get("clinic_data") or {}).get("connector") or {})
        err = _validate_connector(cfg)
        if err:
            raise HTTPException(400, err)
    else:
        cfg = None  # native = no external connector
    if body.get("test"):
        synthetic = {"id": tenant_id, "clinic_data": {"connector": cfg} if cfg else {}}
        try:
            result = await _to_thread(lambda s: connectors_mod.probe(connectors_mod.get_connector(s)), synthetic)
        except Exception as e:  # noqa: BLE001
            result = {"ok": False, "detail": str(e)[:300]}
        return {"tested": True, "result": result}
    db.set_tenant_connector(tenant_id, cfg)
    return {"ok": True}


# --------------------------------------------------------------------------- settings
@router.get("/settings")
async def get_settings(request: Request):
    _require_super(request)
    from app import settings as settings_mod
    editable = {k: {"value": settings_mod.get(k) or "", "label": lbl, "group": grp}
                for k, (lbl, grp) in settings_mod.EDITABLE.items()}
    return {"editable": editable, "inventory": settings_mod.inventory_status()}


@router.post("/settings")
async def save_settings(request: Request, body: dict = Body(...)):
    _require_super(request)
    from app import settings as settings_mod
    values = body.get("values") or {}
    for key in settings_mod.EDITABLE:
        if key in values:
            settings_mod.set_value(key, (values.get(key) or "").strip() or None)
    return {"ok": True}


# --------------------------------------------------------------------------- util
async def _to_thread(fn, *args):
    import asyncio
    return await asyncio.to_thread(fn, *args)
