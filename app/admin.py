import asyncio
import html
import logging
from datetime import datetime

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from app.config import ADMIN_PASSWORD, BASE_DIR, TZ
from app.db import (
    conversation_thread,
    list_appointments,
    list_conversations,
    set_appointment_status,
    stats,
)
from app.events import subscribe, unsubscribe

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
    intent_html = f'<span class="text-xs text-slate-400 ml-1">· {html.escape(intent)}</span>' if intent else ""
    needs_human = p.get("needs_human")
    flag_html = '<span class="ml-1 text-red-500 text-xs">· flag</span>' if needs_human else ""
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
