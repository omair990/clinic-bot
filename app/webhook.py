import asyncio
import hashlib
import hmac
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response

from app.ai import process_message
from app.config import (
    ADMIN_WA_NUMBER,
    N8N_EMERGENCY_URL,
    N8N_NEW_APPOINTMENT_URL,
    WA_APP_SECRET,
    WA_VERIFY_TOKEN,
)
from app.db import claim_message_id, log_message, recent_history, save_appointment
from app.events import publish
from app.outbound import post_event
from app.menus import (
    MAIN_MENU_BUTTONS,
    doctors_list_rows,
    main_menu_body,
    services_list_rows,
)
from app.wa_client import mark_read, send_buttons, send_list, send_text

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/webhook")
async def verify(request: Request):
    """Meta sends GET with hub.mode, hub.verify_token, hub.challenge to verify the webhook."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == WA_VERIFY_TOKEN:
        log.info("Webhook verified")
        return Response(content=challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def receive(request: Request, background_tasks: BackgroundTasks):
    """Meta POSTs incoming messages here. Acknowledge fast; process in background."""
    raw_body = await request.body()
    if not _verify_signature(raw_body, request.headers.get("x-hub-signature-256", "")):
        log.warning("Invalid webhook signature from %s", request.client.host if request.client else "?")
        raise HTTPException(status_code=401, detail="Invalid signature")
    import json as _json
    payload = _json.loads(raw_body)
    background_tasks.add_task(_handle_payload, payload)
    return {"status": "received"}


def _verify_signature(body: bytes, header_value: str) -> bool:
    """Verify Meta's X-Hub-Signature-256 (HMAC-SHA256 with app secret)."""
    if not WA_APP_SECRET:
        # If unset, allow through but log loudly. Production MUST set this.
        log.warning("WA_APP_SECRET not configured — signature check skipped")
        return True
    if not header_value.startswith("sha256="):
        return False
    expected = header_value[len("sha256="):]
    computed = hmac.new(WA_APP_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, computed)


async def _handle_payload(payload: dict) -> None:
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []) or []:
                    await _handle_message(msg)
    except Exception:
        log.exception("Failed handling payload")


async def _handle_message(msg: dict) -> None:
    msg_type = msg.get("type")
    sender = msg.get("from")
    msg_id = msg.get("id")

    if msg_id and not claim_message_id(msg_id):
        log.info("Dedup: skipping already-processed message %s", msg_id)
        return

    user_text = ""
    interactive_id = None
    if msg_type == "text":
        user_text = msg.get("text", {}).get("body", "").strip()
    elif msg_type == "interactive":
        inter = msg.get("interactive", {})
        if inter.get("type") == "button_reply":
            br = inter.get("button_reply", {})
            interactive_id = br.get("id")
            user_text = br.get("title", "").strip()
        elif inter.get("type") == "list_reply":
            lr = inter.get("list_reply", {})
            interactive_id = lr.get("id")
            user_text = lr.get("title", "").strip()

    if not user_text:
        await send_text(sender, "Sorry, I couldn't read that. Please type your question.")
        return

    # Hard-routed menu actions before hitting the AI
    if interactive_id == "menu_services":
        await _send_services_menu(sender)
        log_message(sender, "in", user_text)
        log_message(sender, "out", "[services menu]", intent="pricing")
        return
    if interactive_id == "menu_book":
        await _send_doctors_menu(sender)
        log_message(sender, "in", user_text)
        log_message(sender, "out", "[doctors menu]", intent="appointment")
        return

    log.info("In from %s: %s", sender, user_text)
    log_message(sender, "in", user_text)
    publish("message", {"wa_user": sender, "direction": "in", "text": user_text})

    asyncio.create_task(mark_read(msg_id))

    history = recent_history(sender, limit=10)

    try:
        ai = await asyncio.to_thread(process_message, user_text, history[:-1])
    except Exception:
        log.exception("AI failed")
        await send_text(sender, "Sorry, we are having a temporary issue. A staff member will get back to you shortly.")
        if ADMIN_WA_NUMBER:
            await send_text(ADMIN_WA_NUMBER, f"AI error for {sender}: {user_text!r}")
        return

    await send_text(sender, ai.reply)
    log_message(sender, "out", ai.reply, intent=ai.intent, needs_human=ai.needs_human)
    publish("message", {"wa_user": sender, "direction": "out", "text": ai.reply,
                        "intent": ai.intent, "needs_human": ai.needs_human})

    # Show main menu on greeting or first-contact
    if ai.intent == "greeting" or len(history) <= 1:
        await _send_main_menu(sender)

    if ai.intent == "appointment" and ai.appointment:
        appt_id = save_appointment(
            wa_user=sender,
            patient_name=ai.appointment.patient_name,
            doctor=ai.appointment.doctor,
            service=ai.appointment.service,
            requested_datetime=ai.appointment.requested_datetime,
            notes=ai.appointment.notes,
        )
        log.info("Saved appointment #%s for %s", appt_id, sender)
        await post_event(N8N_NEW_APPOINTMENT_URL, {
            "event": "new_appointment",
            "appointment_id": appt_id,
            "wa_user": sender,
            "patient_name": ai.appointment.patient_name,
            "doctor": ai.appointment.doctor,
            "service": ai.appointment.service,
            "requested_datetime": ai.appointment.requested_datetime,
            "notes": ai.appointment.notes,
        })

    if (ai.intent in ("emergency", "handover") or ai.needs_human) and ADMIN_WA_NUMBER:
        flag = "EMERGENCY" if ai.intent == "emergency" else "HANDOVER"
        await send_text(
            ADMIN_WA_NUMBER,
            f"[{flag}] {sender}\nUser: {user_text}\nAI replied: {ai.reply}",
        )

    if ai.intent == "emergency" or ai.needs_human:
        await post_event(N8N_EMERGENCY_URL, {
            "event": "needs_attention",
            "kind": ai.intent if ai.intent in ("emergency", "handover") else "needs_human",
            "wa_user": sender,
            "user_message": user_text,
            "ai_reply": ai.reply,
        })


async def _send_main_menu(to: str) -> None:
    try:
        await send_buttons(to, main_menu_body(), MAIN_MENU_BUTTONS)
    except Exception:
        log.exception("send main menu failed")


async def _send_services_menu(to: str) -> None:
    try:
        await send_list(
            to,
            "Choose a service to learn more about pricing and duration.",
            "View Services",
            services_list_rows(),
            header="Our Services",
        )
    except Exception:
        log.exception("send services menu failed")


async def _send_doctors_menu(to: str) -> None:
    try:
        await send_list(
            to,
            "Pick the doctor you'd like to see — I'll then ask about service and time.",
            "Pick Doctor",
            doctors_list_rows(),
            header="Our Doctors",
        )
    except Exception:
        log.exception("send doctors menu failed")
