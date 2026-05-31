import asyncio
import html
import logging
from datetime import datetime

import psycopg
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

import json

from app.config import (
    ADMIN_PASSWORD,
    BASE_DIR,
    NO_SHOW_AUTO_SEND,
    NO_SHOW_PREDICTOR,
    NOTIFY_ON_STATUS_CHANGE,
    TZ,
)
from app.auth import hash_password, verify_password
from app.db import (
    admin_set_appointment_status,
    conversation_thread,
    create_tenant,
    get_appointment_by_id,
    get_followup,
    get_tenant,
    get_tenant_by_username,
    list_appointments,
    list_conversations,
    list_events,
    list_no_show_followups,
    list_plans,
    list_reviews,
    list_tenants,
    review_stats,
    no_show_count_since,
    no_show_reason_breakdown,
    resolve_event,
    risk_band_counts,
    set_appointment_status,
    set_followup_stage,
    set_tenant_connector,
    set_tenant_credentials,
    set_tenant_plan,
    set_tenant_status,
    staff_username_taken,
    stats,
    unresolved_event_count,
    update_tenant_config,
    upsert_plan,
)
from app.db import tenant_id_for_user
from app.events import subscribe, unsubscribe
from app import analysis as analysis_mod
from app import connectors as connectors_mod
from app import incidents
from app import insights as insights_mod
from app import no_show as no_show_mod
from app.notifications import notify_appointment_status
from app.tenancy import current_period

log = logging.getLogger(__name__)
router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

APPOINTMENT_STATUSES = {"confirmed", "cancelled", "completed", "no_show"}


def _fmt_dt(value) -> str:
    """Render a timestamp (datetime or ISO string) in clinic local time."""
    if value is None:
        return "—"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    if isinstance(value, datetime):
        return value.astimezone(TZ).strftime("%Y-%m-%d %H:%M")
    return str(value)


templates.env.filters["fmt_dt"] = _fmt_dt


# --- Message classification badges (shared by templates + live SSE feed) ---
INTENT_BADGES = {
    "emergency":   ("🚨 Emergency",   "bg-red-100 text-red-700 ring-red-200"),
    "handover":    ("🙋 Handover",    "bg-amber-100 text-amber-700 ring-amber-200"),
    "appointment": ("📅 Appointment", "bg-emerald-100 text-emerald-700 ring-emerald-200"),
    "no_show":     ("🔁 No-show",     "bg-rose-100 text-rose-700 ring-rose-200"),
    "chat":        ("💬 Chat",        "bg-slate-100 text-slate-600 ring-slate-200"),
    "error":       ("⚠️ Error",        "bg-red-100 text-red-700 ring-red-200"),
}


def intent_badge_html(intent: str | None) -> str:
    """A small coloured pill for a message's classification. Returns '' if none."""
    if not intent:
        return ""
    label, classes = INTENT_BADGES.get(
        intent, (intent.replace("_", " ").title(), "bg-slate-100 text-slate-600 ring-slate-200"))
    return (
        f'<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full '
        f'text-[10px] font-medium ring-1 ring-inset {classes}">{html.escape(label)}</span>'
    )


templates.env.filters["intent_badge"] = lambda i: Markup(intent_badge_html(i))


# --- Lead-score badges (Hot / Warm / Cold) ---
LEAD_BADGES = {
    "hot":  ("🔥 Hot",  "bg-rose-100 text-rose-700 ring-rose-200"),
    "warm": ("🌤️ Warm", "bg-amber-100 text-amber-700 ring-amber-200"),
    "cold": ("❄️ Cold", "bg-sky-100 text-sky-700 ring-sky-200"),
}


def lead_badge_html(band: str | None) -> str:
    if not band or band not in LEAD_BADGES:
        return ""
    label, classes = LEAD_BADGES[band]
    return (f'<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full '
            f'text-[10px] font-medium ring-1 ring-inset {classes}">{html.escape(label)}</span>')


templates.env.filters["lead_badge"] = lambda b: Markup(lead_badge_html(b))


# --- Connector labels (which appointment backend a clinic is on) ---
CONNECTOR_LABELS = {
    "native": "🗄️ Native (our DB)",
    "google_calendar": "📅 Google Calendar",
    "cliniko": "🩺 Cliniko",
    "custom_erp": "🔌 Custom ERP",
    "fhir": "🏥 FHIR / HIS",
}
templates.env.filters["connector_label"] = lambda c: CONNECTOR_LABELS.get(c or "native",
                                                                          c or "native")


def _principal(request: Request) -> dict | None:
    role = request.session.get("role")
    if not role:
        return None
    return {"role": role, "tenant_id": request.session.get("tenant_id"),
            "tenant_name": request.session.get("tenant_name")}


def _require_auth(request: Request) -> dict:
    p = _principal(request)
    if not p:
        raise HTTPException(status_code=302, headers={"Location": "/admin/login"})
    return p


def _require_super(request: Request) -> None:
    if _require_auth(request)["role"] != "super":
        raise HTTPException(status_code=403, detail="Super-admin only")


def _scope(request: Request) -> int | None:
    """tenant_id to scope queries to, or None for super-admin (sees all)."""
    p = _require_auth(request)
    return p["tenant_id"] if p["role"] == "clinic" else None


def _open_issue_count(request: Request) -> int:
    """Unresolved issues for the sidebar badge — never raises (0 on any error)."""
    try:
        p = _principal(request)
        if not p:
            return 0
        scope = p["tenant_id"] if p["role"] == "clinic" else None
        return unresolved_event_count(scope)
    except Exception:  # noqa: BLE001
        return 0


templates.env.globals["open_issue_count"] = _open_issue_count


def _wa_send_failing() -> bool:
    """Whether outbound WhatsApp is currently failing auth — drives the dashboard banner.
    Never raises (a banner check must not break the page)."""
    try:
        from app.wa_client import auth_failing
        return auth_failing()
    except Exception:  # noqa: BLE001
        return False


templates.env.globals["wa_send_failing"] = _wa_send_failing
templates.env.filters["reason_label"] = lambda r: no_show_mod.REASON_LABELS.get(r, r or "—")


def _month_start():
    """First moment of the current month in clinic time — the 'This month' window."""
    now = datetime.now(TZ)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("role"):
        return RedirectResponse("/admin/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
async def do_login(request: Request, username: str = Form(""), password: str = Form(...)):
    username = username.strip()
    # No username => platform super-admin password.
    if not username and password == ADMIN_PASSWORD:
        request.session.clear()
        request.session["role"] = "super"
        return RedirectResponse("/admin/", status_code=303)
    # Username => per-clinic staff login.
    if username:
        t = get_tenant_by_username(username)
        if t and verify_password(password, t.get("staff_password_hash")):
            request.session.clear()
            request.session.update(
                {"role": "clinic", "tenant_id": t["id"], "tenant_name": t["name"]})
            return RedirectResponse("/admin/", status_code=303)
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": "Invalid credentials"}, status_code=401
    )


@router.post("/logout")
async def do_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    _require_auth(request)
    scope = _scope(request)
    return templates.TemplateResponse(
        "home.html", {"request": request, "stats": stats(scope),
                      "no_shows_month": no_show_count_since(_month_start(), scope)}
    )


@router.get("/conversations", response_class=HTMLResponse)
async def conversations(request: Request):
    _require_auth(request)
    return templates.TemplateResponse(
        "conversations.html",
        {"request": request, "rows": list_conversations(tenant_id=_scope(request))},
    )


async def _conversation_analysis(request: Request, wa_user: str, force: bool = False):
    """Build/fetch the AI summary + lead score for a conversation. Tenant-scoped; for the
    super-admin we resolve the tenant from the conversation itself. Never raises."""
    scope = _scope(request)
    tid = scope if scope is not None else tenant_id_for_user(wa_user)
    if not tid:
        return None
    try:
        return await asyncio.to_thread(analysis_mod.get_or_build, tid, wa_user, force)
    except Exception:  # noqa: BLE001 — analysis is best-effort, never block the page
        log.exception("conversation analysis failed for %s", wa_user)
        return None


@router.get("/conversations/{wa_user}", response_class=HTMLResponse)
async def conversation_view(request: Request, wa_user: str):
    _require_auth(request)
    return templates.TemplateResponse(
        "conversation_detail.html",
        {"request": request, "wa_user": wa_user,
         "messages": conversation_thread(wa_user, tenant_id=_scope(request)),
         "analysis": await _conversation_analysis(request, wa_user)},
    )


@router.post("/conversations/{wa_user}/analysis/refresh")
async def refresh_analysis(request: Request, wa_user: str):
    _require_auth(request)
    await _conversation_analysis(request, wa_user, force=True)
    return RedirectResponse(f"/admin/conversations/{wa_user}", status_code=303)


def _render_bubble(p: dict) -> str:
    """A single chat bubble for the live conversation view (SSE — one line, no raw \\n)."""
    text = html.escape(p.get("text", "")).replace("\n", "<br>")
    if p.get("direction") == "in":
        mic = '🎤 ' if p.get("source") == "voice" else ''
        return (
            '<div class="flex justify-start"><div class="max-w-md">'
            f'<div class="px-3 py-2 rounded-lg rounded-tl-sm bg-slate-100 text-slate-900 text-sm">{mic}{text}</div>'
            '<div class="text-[10px] text-slate-400 mt-1">now</div></div></div>'
        )
    badge = intent_badge_html(p.get("intent")) if p.get("intent") else ""
    flag = ('<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] '
            'font-medium ring-1 ring-inset bg-red-100 text-red-700 ring-red-200">flag</span>'
            if p.get("needs_human") else "")
    return (
        '<div class="flex justify-end"><div class="max-w-md">'
        f'<div class="px-3 py-2 rounded-lg rounded-tr-sm bg-emerald-600 text-white text-sm">{text}</div>'
        f'<div class="mt-1 flex items-center justify-end gap-1.5">{badge}{flag}'
        '<span class="text-[10px] text-slate-400">now</span></div></div></div>'
    )


_TYPING_BUBBLE = (
    '<div class="flex justify-end"><div class="px-3 py-2 rounded-lg rounded-tr-sm '
    'bg-emerald-50 text-emerald-700 text-sm italic">typing<span class="pulse-dot ml-1"></span></div></div>'
)


@router.get("/conversations/{wa_user}/stream")
async def conversation_stream(request: Request, wa_user: str):
    scope = _scope(request)
    q = subscribe()

    async def gen():
        import json as _json
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=20.0)
                    p = _json.loads(payload)
                    if p.get("wa_user") != wa_user:
                        continue
                    if scope is not None and p.get("tenant_id") != scope:
                        continue
                    kind = p.get("type")
                    if kind == "message":
                        yield f"event: message\ndata: {_render_bubble(p)}\n\n"
                    elif kind == "typing":
                        yield f"event: typing\ndata: {_TYPING_BUBBLE}\n\n"
                    elif kind == "stoptyping":
                        yield "event: stoptyping\ndata: <span></span>\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/appointments", response_class=HTMLResponse)
async def appointments(request: Request, status: str | None = None):
    _require_auth(request)
    return templates.TemplateResponse(
        "appointments.html",
        {"request": request, "rows": list_appointments(status, tenant_id=_scope(request)),
         "filter_status": status},
    )


@router.post("/appointments/{appointment_id}/status")
async def update_appointment(request: Request, appointment_id: int, status: str = Form(...)):
    scope = _scope(request)
    if status not in APPOINTMENT_STATUSES:
        raise HTTPException(400, "bad status")
    appt = get_appointment_by_id(appointment_id)   # read details + prior status first
    prior = appt["status"] if appt else None
    if scope is None:
        admin_set_appointment_status(appointment_id, status)
    else:
        set_appointment_status(scope, appointment_id, status)  # clinic can only touch its own

    # Let the patient know when staff cancel or complete their appointment here.
    notify = (NOTIFY_ON_STATUS_CHANGE and appt and status != prior
              and status in ("cancelled", "completed")
              and (scope is None or appt["tenant_id"] == scope))
    if notify:
        try:
            tenant = get_tenant(appt["tenant_id"])
            if tenant:
                await notify_appointment_status(appt, status, tenant)
        except Exception as e:  # noqa: BLE001 — a send failure must not break the action
            log.warning("status-change notify failed for appt %s: %s", appointment_id, str(e)[:160])
            await asyncio.to_thread(
                incidents.record, "whatsapp", "Appointment status notification failed",
                level="warning", detail=str(e)[:300],
                tenant_id=appt["tenant_id"], wa_user=appt.get("wa_user"))
    referrer = request.headers.get("referer", "/admin/appointments")
    return RedirectResponse(referrer, status_code=303)


@router.get("/no-shows", response_class=HTMLResponse)
async def no_shows_page(request: Request):
    _require_auth(request)
    scope = _scope(request)
    since = _month_start()
    return templates.TemplateResponse(
        "no_shows.html",
        {"request": request,
         "rows": list_no_show_followups(tenant_id=scope),
         "month_count": no_show_count_since(since, scope),
         "reasons": no_show_reason_breakdown(since, scope),
         "risk": risk_band_counts(scope),
         "predictor_on": NO_SHOW_PREDICTOR,
         "auto_send": NO_SHOW_AUTO_SEND},
    )


@router.post("/no-shows/{followup_id}/action")
async def no_show_action(request: Request, followup_id: int, action: str = Form(...)):
    scope = _scope(request)
    fu = get_followup(followup_id, tenant_id=scope)  # enforces tenant ownership
    if not fu:
        raise HTTPException(404, "Follow-up not found")
    if action in ("send", "resend"):
        tenant = get_tenant(fu["tenant_id"])
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
        set_followup_stage(followup_id, "resolved", stamp="resolved_at")
    elif action == "inactive":
        set_followup_stage(followup_id, "inactive", stamp="resolved_at")
    return RedirectResponse(request.headers.get("referer", "/admin/no-shows"), status_code=303)


def _render_plans(request: Request, *, error: str | None = None, status_code: int = 200):
    """Render the Plans & Usage page (optionally with an error banner)."""
    period = current_period(str(TZ))
    return templates.TemplateResponse(
        "plans.html",
        {"request": request, "plans": list_plans(),
         "tenants": list_tenants(period), "period": period, "error": error},
        status_code=status_code,
    )


@router.get("/reviews", response_class=HTMLResponse)
async def reviews_page(request: Request):
    _require_auth(request)
    scope = _scope(request)
    return templates.TemplateResponse(
        "reviews.html",
        {"request": request, "rows": list_reviews(tenant_id=scope),
         "stats": review_stats(scope)})


@router.get("/insights", response_class=HTMLResponse)
async def insights_page(request: Request, period: str = "day"):
    _require_auth(request)
    scope = _scope(request)
    report = await asyncio.to_thread(insights_mod.report, scope, period, str(TZ))
    return templates.TemplateResponse(
        "insights.html", {"request": request, "report": report})


def _build_connector_config(ctype: str, form, existing: dict):
    """Assemble a connector config dict from the form. Secrets left blank keep their existing
    value (we never echo secrets back to the form). Returns (config|None, error|None);
    config None means 'native' (no external connector)."""
    existing = existing or {}

    def secret(field, key, src=None):
        v = (form.get(field) or "").strip()
        return v or (src or existing).get(key)

    def jmap(field, label):
        raw = (form.get(field) or "").strip()
        if not raw:
            return {}, None
        try:
            d = json.loads(raw)
        except json.JSONDecodeError as e:
            return None, f"{label}: invalid JSON ({e})"
        return (d, None) if isinstance(d, dict) else (None, f"{label} must be a JSON object")

    if ctype == "native":
        return None, None

    def with_webhook(cfg):
        ws = secret("webhook_secret", "webhook_secret")
        if ws:
            cfg["webhook_secret"] = ws
        return cfg

    if ctype == "google_calendar":
        cals, err = jmap("g_calendars", "Calendars (doctor → calendarId)")
        if err:
            return None, err
        cfg = {"type": "google_calendar",
               "timezone": (form.get("g_timezone") or "Asia/Riyadh").strip() or "Asia/Riyadh",
               "calendars": cals}
        rt = secret("g_refresh_token", "refresh_token")
        if rt:
            cfg["refresh_token"] = rt
        if (form.get("g_default_calendar") or "").strip():
            cfg["default_calendar"] = form["g_default_calendar"].strip()
        if not cfg.get("refresh_token"):
            return None, "Refresh token is required for Google Calendar."
        return with_webhook(cfg), None
    if ctype == "cliniko":
        pr, err = jmap("c_practitioners", "Practitioners")
        if err:
            return None, err
        at, err = jmap("c_appointment_types", "Appointment types")
        if err:
            return None, err
        cfg = {"type": "cliniko", "business_id": (form.get("c_business_id") or "").strip(),
               "user_agent": (form.get("c_user_agent") or "").strip() or "ClinicAIAssistant",
               "practitioners": pr, "appointment_types": at}
        ak = secret("c_api_key", "api_key")
        if ak:
            cfg["api_key"] = ak
        if not cfg.get("api_key"):
            return None, "API key is required for Cliniko."
        if not cfg["business_id"]:
            return None, "Business id is required for Cliniko."
        return with_webhook(cfg), None
    if ctype == "custom_erp":
        base = (form.get("e_base_url") or "").strip()
        if not base:
            return None, "Base URL is required for Custom ERP."
        atype = (form.get("e_auth_type") or "none").strip()
        ex_auth = existing.get("auth") or {}
        auth = {"type": atype}
        if atype == "bearer":
            tok = secret("e_token", "token", ex_auth)
            if tok:
                auth["token"] = tok
        elif atype == "header":
            auth["name"] = (form.get("e_header_name") or "").strip() or "X-API-Key"
            val = secret("e_header_value", "value", ex_auth)
            if val:
                auth["value"] = val
        return with_webhook({"type": "custom_erp", "base_url": base, "auth": auth}), None
    if ctype == "fhir":
        base = (form.get("f_base_url") or "").strip()
        if not base:
            return None, "Base URL is required for FHIR."
        sch, err = jmap("f_schedules", "Schedules")
        if err:
            return None, err
        pr, err = jmap("f_practitioners", "Practitioners")
        if err:
            return None, err
        atype = (form.get("f_auth_type") or "none").strip()
        ex_auth = existing.get("auth") or {}
        auth = {"type": atype}
        if atype == "bearer":
            tok = secret("f_token", "token", ex_auth)
            if tok:
                auth["token"] = tok
        elif atype == "client_credentials":
            auth.update({"token_url": (form.get("f_token_url") or "").strip(),
                         "client_id": (form.get("f_client_id") or "").strip(),
                         "scope": (form.get("f_scope") or "").strip()})
            cs = secret("f_client_secret", "client_secret", ex_auth)
            if cs:
                auth["client_secret"] = cs
        return with_webhook({"type": "fhir", "base_url": base, "auth": auth,
                             "booking_status": (form.get("f_booking_status") or "booked").strip(),
                             "schedules": sch, "practitioners": pr}), None
    return None, f"Unknown connector type: {ctype}"


def _render_connector(request, t, ctype, conn, result=None, error=None, status_code=200):
    return templates.TemplateResponse(
        "connector_form.html",
        {"request": request, "t": t, "ctype": ctype, "conn": conn or {},
         "result": result, "error": error}, status_code=status_code)


@router.get("/tenants/{tenant_id}/connector", response_class=HTMLResponse)
async def connector_page(request: Request, tenant_id: int):
    _require_super(request)
    t = get_tenant(tenant_id)
    if not t:
        raise HTTPException(404, "Tenant not found")
    conn = (t.get("clinic_data") or {}).get("connector") or {}
    return _render_connector(request, t, conn.get("type", "native"), conn)


@router.post("/tenants/{tenant_id}/connector")
async def connector_save(request: Request, tenant_id: int):
    _require_super(request)
    t = get_tenant(tenant_id)
    if not t:
        raise HTTPException(404, "Tenant not found")
    form = await request.form()
    action = form.get("action", "save")
    ctype = (form.get("connector_type") or "native").strip()
    existing = (t.get("clinic_data") or {}).get("connector") or {}
    cfg, err = _build_connector_config(ctype, form, existing)
    if err:
        return _render_connector(request, t, ctype, existing, error=err, status_code=400)

    if action == "test":
        synthetic = {"id": tenant_id, "clinic_data": {"connector": cfg} if cfg else {}}
        try:
            result = connectors_mod.probe(connectors_mod.get_connector(synthetic))
        except Exception as e:  # noqa: BLE001
            result = {"ok": False, "detail": str(e)[:300]}
        return _render_connector(request, t, ctype, cfg or {}, result=result)

    set_tenant_connector(tenant_id, cfg)
    return RedirectResponse(f"/admin/tenants/{tenant_id}/connector", status_code=303)


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, saved: str = ""):
    _require_super(request)
    from app import settings as settings_mod
    editable = {k: (settings_mod.get(k) or "", lbl, grp)
                for k, (lbl, grp) in settings_mod.EDITABLE.items()}
    return templates.TemplateResponse(
        "settings.html", {"request": request, "inventory": settings_mod.inventory_status(),
                          "editable": editable, "saved": saved})


@router.post("/settings")
async def settings_save(request: Request):
    _require_super(request)
    from app import settings as settings_mod
    form = await request.form()
    for key in settings_mod.EDITABLE:
        if key in form:
            settings_mod.set_value(key, (form.get(key) or "").strip() or None)
    return RedirectResponse("/admin/settings?saved=1", status_code=303)


@router.get("/plans", response_class=HTMLResponse)
async def plans_page(request: Request):
    _require_super(request)
    return _render_plans(request)


def _int_or_none(value: str) -> int | None:
    value = (value or "").strip()
    return int(value) if value else None


@router.post("/plans")
async def save_plan(request: Request,
                    name: str = Form(...),
                    monthly_text_quota: str = Form(""),
                    monthly_voice_quota: str = Form(""),
                    trial_days: str = Form(""),
                    price_sar: str = Form(""),
                    voice_enabled: str = Form("off"),
                    is_trial: str = Form("off")):
    _require_super(request)
    upsert_plan(
        name.strip(),
        _int_or_none(monthly_text_quota),
        voice_enabled == "on",
        _int_or_none(monthly_voice_quota),
        is_trial == "on",
        _int_or_none(trial_days),
        _int_or_none(price_sar),
    )
    return RedirectResponse("/admin/plans", status_code=303)


@router.post("/tenants/{tenant_id}/plan")
async def assign_plan(request: Request, tenant_id: int, plan_id: int = Form(...)):
    _require_super(request)
    set_tenant_plan(tenant_id, plan_id)
    return RedirectResponse("/admin/plans", status_code=303)


@router.post("/tenants/{tenant_id}/status")
async def change_tenant_status(request: Request, tenant_id: int, status: str = Form(...)):
    _require_super(request)
    if status in {"active", "suspended", "expired"}:
        set_tenant_status(tenant_id, status)
    return RedirectResponse("/admin/plans", status_code=303)


def _parse_clinic_data(raw: str) -> dict | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Invalid clinic data JSON: {e}")
    if not isinstance(data, dict):
        raise HTTPException(400, "Clinic data must be a JSON object")
    return data


@router.post("/tenants")
async def add_tenant(request: Request,
                     name: str = Form(...),
                     slug: str = Form(...),
                     wa_phone_number_id: str = Form(""),
                     plan_id: int = Form(...),
                     timezone: str = Form("Asia/Riyadh"),
                     wa_access_token: str = Form(""),
                     clinic_data: str = Form(""),
                     staff_username: str = Form(""),
                     staff_password: str = Form("")):
    _require_super(request)
    uname = staff_username.strip() or None
    if uname and staff_username_taken(uname):
        return _render_plans(request, status_code=409,
                             error=f'Staff username "{uname}" is already in use by '
                             "another clinic. Choose a different one.")
    try:
        tid = create_tenant(name.strip(), slug.strip(), wa_phone_number_id.strip() or None,
                            plan_id, timezone.strip() or "Asia/Riyadh",
                            wa_access_token.strip() or None, _parse_clinic_data(clinic_data))
    except psycopg.errors.UniqueViolation as e:
        log.warning("create_tenant rejected (duplicate): %s", str(e)[:160])
        return _render_plans(request, status_code=409,
                             error="Could not create clinic — the slug, WhatsApp "
                             "number, or staff username is already in use.")
    if uname:
        pw_hash = hash_password(staff_password) if staff_password else None
        set_tenant_credentials(tid, uname, pw_hash)
    return RedirectResponse("/admin/plans", status_code=303)


@router.get("/tenants/{tenant_id}/edit", response_class=HTMLResponse)
async def edit_tenant_page(request: Request, tenant_id: int):
    _require_super(request)
    tenant = get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    pretty = json.dumps(tenant.get("clinic_data") or {}, indent=2, ensure_ascii=False)
    return templates.TemplateResponse(
        "tenant_edit.html", {"request": request, "t": tenant, "clinic_json": pretty})


def _render_tenant_edit(request: Request, tenant_id: int, *, name, wa_phone_number_id,
                        timezone, wa_access_token, clinic_data_raw, staff_username, error):
    """Re-render the clinic edit form with an error, preserving what was just typed."""
    existing = get_tenant(tenant_id)
    t = {"id": tenant_id, "name": name, "slug": (existing or {}).get("slug", ""),
         "wa_phone_number_id": wa_phone_number_id, "timezone": timezone,
         "wa_access_token": wa_access_token, "staff_username": staff_username}
    clinic_json = clinic_data_raw if clinic_data_raw.strip() else json.dumps(
        (existing or {}).get("clinic_data") or {}, indent=2, ensure_ascii=False)
    return templates.TemplateResponse(
        "tenant_edit.html",
        {"request": request, "t": t, "clinic_json": clinic_json, "error": error},
        status_code=409)


@router.post("/tenants/{tenant_id}/edit")
async def edit_tenant(request: Request, tenant_id: int,
                      name: str = Form(...),
                      wa_phone_number_id: str = Form(""),
                      timezone: str = Form("Asia/Riyadh"),
                      wa_access_token: str = Form(""),
                      clinic_data: str = Form(""),
                      staff_username: str = Form(""),
                      staff_password: str = Form("")):
    _require_super(request)
    uname = staff_username.strip() or None
    # Check the username up front so we don't half-save the config then 500 on the
    # UNIQUE constraint. (The try/except below is a backstop for the rare race.)
    if uname and staff_username_taken(uname, exclude_tenant_id=tenant_id):
        return _render_tenant_edit(
            request, tenant_id, name=name, wa_phone_number_id=wa_phone_number_id,
            timezone=timezone, wa_access_token=wa_access_token, clinic_data_raw=clinic_data,
            staff_username=staff_username,
            error=f'Staff username "{uname}" is already in use by another clinic.')

    update_tenant_config(tenant_id, name=name.strip(),
                         wa_phone_number_id=wa_phone_number_id.strip() or None,
                         wa_access_token=wa_access_token.strip() or None,
                         timezone=timezone.strip() or "Asia/Riyadh",
                         clinic_data=_parse_clinic_data(clinic_data))
    # Update credentials: username always; password only if a new one was typed.
    pw_hash = hash_password(staff_password) if staff_password.strip() else None
    try:
        set_tenant_credentials(tenant_id, uname, pw_hash)
    except psycopg.errors.UniqueViolation:
        return _render_tenant_edit(
            request, tenant_id, name=name, wa_phone_number_id=wa_phone_number_id,
            timezone=timezone, wa_access_token=wa_access_token, clinic_data_raw=clinic_data,
            staff_username=staff_username,
            error=f'Staff username "{uname}" is already in use by another clinic.')
    return RedirectResponse("/admin/plans", status_code=303)


@router.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request, show: str = "open"):
    _require_auth(request)
    scope = _scope(request)
    resolved = {"open": False, "resolved": True}.get(show, None)
    return templates.TemplateResponse(
        "logs.html",
        {"request": request, "show": show,
         "events": list_events(resolved=resolved, tenant_id=scope),
         "open_count": unresolved_event_count(scope)},
    )


@router.post("/logs/{event_id}/resolve")
async def resolve_log(request: Request, event_id: int):
    scope = _scope(request)
    resolve_event(event_id, tenant_id=scope)  # clinic can only resolve its own
    return RedirectResponse(request.headers.get("referer", "/admin/logs"), status_code=303)


@router.get("/stream")
async def stream(request: Request):
    scope = _scope(request)   # clinic sees only its own events; super sees all
    q = subscribe()

    async def gen():
        import json as _json
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=20.0)
                    _p = _json.loads(payload)
                    if _p.get("type") != "message":
                        continue  # ignore typing/stoptyping on the home feed
                    if scope is not None and _p.get("tenant_id") != scope:
                        continue
                    yield f"event: message\ndata: {_render_event(payload)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream")


def _render_event(payload_json: str) -> str:
    """Render an event as a small HTML row for HTMX swap. Must be a single SSE data: line."""
    import json
    p = json.loads(payload_json)
    direction = p.get("direction", "?")
    wa = p.get("wa_user", "?")
    text = html.escape(p.get("text", ""))[:200]
    intent = p.get("intent")
    arrow = "←" if direction == "in" else "→"
    color = "text-slate-700" if direction == "in" else "text-emerald-700"
    intent_html = f'<span class="ml-2 align-middle">{intent_badge_html(intent)}</span>' if intent else ""
    needs_human = p.get("needs_human")
    flag_html = (
        '<span class="ml-1 align-middle inline-flex items-center px-2 py-0.5 rounded-full '
        'text-[10px] font-medium ring-1 ring-inset bg-red-100 text-red-700 ring-red-200">flag</span>'
        if needs_human else ""
    )
    html_row = (
        f'<div class="px-4 py-2 hover:bg-slate-50">'
        f'<span class="text-xs text-slate-400 mr-2">{arrow}</span>'
        f'<a href="/admin/conversations/{wa}" class="font-medium hover:underline">+{wa}</a>'
        f'<span class="{color} ml-2">{text}</span>'
        f'{intent_html}{flag_html}'
        f'</div>'
    )
    # SSE data must not contain raw newlines
    return html_row.replace("\n", " ")
