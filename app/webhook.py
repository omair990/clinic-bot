"""WhatsApp webhook: verify, authenticate, and route inbound messages through the agent."""
import asyncio
import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response

from app.agent import run_agent
from app.config import ADMIN_WA_NUMBER, WA_APP_SECRET, WA_VERIFY_TOKEN
from app.db import claim_message_id, log_message, recent_history
from app.events import publish
from app.tools import AgentContext
from app.wa_client import mark_read, send_text

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/webhook")
async def verify(request: Request):
    """Meta verification handshake."""
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == WA_VERIFY_TOKEN:
        log.info("Webhook verified")
        return Response(content=params.get("hub.challenge"), media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def receive(request: Request, background_tasks: BackgroundTasks):
    """Acknowledge fast, process in the background (Meta retries on slow/failed responses)."""
    raw_body = await request.body()
    if not _verify_signature(raw_body, request.headers.get("x-hub-signature-256", "")):
        log.warning("Invalid webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")
    payload = json.loads(raw_body)
    background_tasks.add_task(_handle_payload, payload)
    return {"status": "received"}


def _verify_signature(body: bytes, header_value: str) -> bool:
    if not WA_APP_SECRET:
        log.warning("WA_APP_SECRET not configured — signature check skipped (set it in production)")
        return True
    if not header_value.startswith("sha256="):
        return False
    expected = header_value[len("sha256="):]
    computed = hmac.new(WA_APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, computed)


async def _handle_payload(payload: dict) -> None:
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                for msg in change.get("value", {}).get("messages", []) or []:
                    await _handle_message(msg)
    except Exception:
        log.exception("Failed handling payload")


def _extract_text(msg: dict) -> str:
    if msg.get("type") == "text":
        return msg.get("text", {}).get("body", "").strip()
    if msg.get("type") == "interactive":
        inter = msg.get("interactive", {})
        for key in ("button_reply", "list_reply"):
            if key in inter:
                return inter[key].get("title", "").strip()
    return ""


async def _handle_message(msg: dict) -> None:
    sender = msg.get("from")
    msg_id = msg.get("id")
    if not sender:
        return

    if msg_id and not await asyncio.to_thread(claim_message_id, msg_id):
        log.info("Dedup: skipping %s", msg_id)
        return

    user_text = _extract_text(msg)
    if not user_text:
        await send_text(sender, "Sorry, I couldn't read that. Please type your question.")
        return

    log.info("In  %s: %s", sender, user_text)
    history = await asyncio.to_thread(recent_history, sender, 12)
    await asyncio.to_thread(log_message, sender, "in", user_text)
    publish("message", {"wa_user": sender, "direction": "in", "text": user_text})
    asyncio.create_task(mark_read(msg_id))

    try:
        ctx: AgentContext = await asyncio.to_thread(run_agent, sender, user_text, history)
    except Exception:
        log.exception("Agent failed for %s", sender)
        await send_text(sender,
                        "Sorry, we're having a temporary issue. A staff member will follow up shortly.")
        await asyncio.to_thread(log_message, sender, "out", "[agent error]",
                                "error", True)
        await _notify_admin(f"[AGENT ERROR] +{sender}\nUser: {user_text}")
        return

    await send_text(sender, ctx.reply)
    log.info("Out %s: %s", sender, ctx.reply)
    await asyncio.to_thread(log_message, sender, "out", ctx.reply,
                            ctx.derived_intent(), ctx.needs_human)
    publish("message", {"wa_user": sender, "direction": "out", "text": ctx.reply,
                        "intent": ctx.derived_intent(), "needs_human": ctx.needs_human})

    if ctx.needs_human:
        flag = "EMERGENCY" if ctx.emergency else "HANDOVER"
        await _notify_admin(
            f"[{flag}] +{sender}\nReason: {ctx.escalation_reason}\n"
            f"User: {user_text}\nAI: {ctx.reply}")
    elif ctx.booked_ids or ctx.changed_ids:
        await _notify_admin(f"[BOOKING] +{sender}\n" + "\n".join(ctx.actions))


async def _notify_admin(text: str) -> None:
    if not ADMIN_WA_NUMBER:
        return
    try:
        await send_text(ADMIN_WA_NUMBER, text)
    except Exception:
        log.exception("Failed to notify admin")
