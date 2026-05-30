import asyncio
import html
import logging
from datetime import datetime

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from app.config import ADMIN_PASSWORD, BASE_DIR, TZ
from app.db import (
    conversation_thread,
    list_appointments,
    list_conversations,
    list_plans,
    list_tenants,
    set_appointment_status,
    set_tenant_plan,
    set_tenant_status,
    stats,
    upsert_plan,
)
from app.events import subscribe, unsubscribe
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


def _require_auth(request: Request) -> None:
    if not request.session.get("admin"):
        raise HTTPException(status_code=302, headers={"Location": "/admin/login"})


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("admin"):
        return RedirectResponse("/admin/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
async def do_login(request: Request, password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        request.session["admin"] = True
        return RedirectResponse("/admin/", status_code=303)
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": "Wrong password"}, status_code=401
    )


@router.post("/logout")
async def do_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    _require_auth(request)
    return templates.TemplateResponse(
        "home.html", {"request": request, "stats": stats()}
    )


@router.get("/conversations", response_class=HTMLResponse)
async def conversations(request: Request):
    _require_auth(request)
    return templates.TemplateResponse(
        "conversations.html", {"request": request, "rows": list_conversations()}
    )


@router.get("/conversations/{wa_user}", response_class=HTMLResponse)
async def conversation_view(request: Request, wa_user: str):
    _require_auth(request)
    return templates.TemplateResponse(
        "conversation_detail.html",
        {"request": request, "wa_user": wa_user, "messages": conversation_thread(wa_user)},
    )


@router.get("/appointments", response_class=HTMLResponse)
async def appointments(request: Request, status: str | None = None):
    _require_auth(request)
    return templates.TemplateResponse(
        "appointments.html",
        {"request": request, "rows": list_appointments(status), "filter_status": status},
    )


@router.post("/appointments/{appointment_id}/status")
async def update_appointment(request: Request, appointment_id: int, status: str = Form(...)):
    _require_auth(request)
    if status not in APPOINTMENT_STATUSES:
        raise HTTPException(400, "bad status")
    set_appointment_status(appointment_id, status)
    referrer = request.headers.get("referer", "/admin/appointments")
    return RedirectResponse(referrer, status_code=303)


@router.get("/plans", response_class=HTMLResponse)
async def plans_page(request: Request):
    _require_auth(request)
    period = current_period(str(TZ))
    return templates.TemplateResponse(
        "plans.html",
        {"request": request, "plans": list_plans(),
         "tenants": list_tenants(period), "period": period},
    )


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
    _require_auth(request)
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
    _require_auth(request)
    set_tenant_plan(tenant_id, plan_id)
    return RedirectResponse("/admin/plans", status_code=303)


@router.post("/tenants/{tenant_id}/status")
async def change_tenant_status(request: Request, tenant_id: int, status: str = Form(...)):
    _require_auth(request)
    if status in {"active", "suspended", "expired"}:
        set_tenant_status(tenant_id, status)
    return RedirectResponse("/admin/plans", status_code=303)


@router.get("/stream")
async def stream(request: Request):
    _require_auth(request)
    q = subscribe()

    async def gen():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=20.0)
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
