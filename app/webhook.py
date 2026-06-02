"""WhatsApp webhook: verify, authenticate, and route inbound messages through the agent."""
import asyncio
import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response

from app.agent import run_agent
from app import incidents, notify
from app.config import USAGE_ENFORCEMENT, WA_APP_SECRET, WA_VERIFY_TOKEN
from app import connectors
from app.db import (
    claim_message_id,
    get_tenant,
    log_message,
    recent_history,
    set_message_intent,
)
# `notify` here is the routing module (app.notify); the dashboard-bell helper from
# app.events is aliased to publish_notify to avoid the name clash.
from app.events import notify as publish_notify, publish
from app.llm import LLMUnavailable
from app import voice_reply
from app.tenancy import check_quota, record_usage, resolve_tenant
from app.tools import AgentContext
from app.transcribe import transcribe_audio
from app.wa_client import download_media, mark_read, send_text

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
                value = change.get("value", {})
                phone_number_id = value.get("metadata", {}).get("phone_number_id")
                for msg in value.get("messages", []) or []:
                    await _handle_message(msg, phone_number_id)
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


async def _resolve_text(msg: dict, sender: str, creds: dict) -> str | None:
    """Get the user's message as text, transcribing voice notes.

    Returns the text, '' if unreadable (caller sends a generic prompt), or None
    when a voice-specific error reply has already been sent.
    """
    if msg.get("type") != "audio":
        return _extract_text(msg)

    media_id = (msg.get("audio") or {}).get("id")
    if not media_id:
        return ""
    try:
        audio_bytes, mime = await download_media(media_id, access_token=creds.get("access_token"))
        text = (await asyncio.to_thread(transcribe_audio, audio_bytes, mime)).strip()
    except Exception as ex:
        log.exception("Voice transcription failed for %s", sender)
        await asyncio.to_thread(incidents.record, "transcription",
                                "Voice transcription failed", detail=repr(ex), wa_user=sender)
        await send_text(sender, "Sorry, I couldn't process that voice note — "
                                "please type your message or try again.", **creds)
        return None
    if not text:
        await send_text(sender, "Sorry, I couldn't make out that voice note. "
                                "Please try again or type your message.", **creds)
        return None
    log.info("Voice from %s transcribed: %s", sender, text)
    return text


async def _handle_message(msg: dict, phone_number_id: str | None = None) -> None:
    sender = msg.get("from")
    msg_id = msg.get("id")
    if not sender:
        return

    if msg_id and not await asyncio.to_thread(claim_message_id, msg_id):
        log.info("Dedup: skipping %s", msg_id)
        return

    is_voice = msg.get("type") == "audio"
    tenant = await asyncio.to_thread(resolve_tenant, phone_number_id)
    tid = (tenant or {}).get("id") or 0
    creds = {
        "phone_number_id": (tenant or {}).get("wa_phone_number_id"),
        "access_token": (tenant or {}).get("wa_access_token"),
    }

    # Acknowledge + show "typing…" as early as possible (covers transcription time too).
    if msg_id:
        asyncio.create_task(mark_read(msg_id, **creds))

    # Enforce the tenant's plan (status, trial, voice gating, quotas) BEFORE any
    # expensive work (transcription, LLM). Unlimited plan => always allowed.
    if USAGE_ENFORCEMENT:
        decision = await asyncio.to_thread(check_quota, tenant, is_voice=is_voice)
        if not decision.allowed:
            log.info("Blocked %s (tenant %s): %s", sender,
                     tenant.get("id") if tenant else "?", decision.reason)
            await asyncio.to_thread(incidents.record, "quota",
                                    f"Message blocked: {decision.reason}", level="warning",
                                    tenant_id=tid, wa_user=sender)
            await send_text(sender, decision.message, **creds)
            return

    user_text = await _resolve_text(msg, sender, creds)
    if user_text is None:
        return  # a voice-handling error reply was already sent
    if not user_text:
        await send_text(sender, "Sorry, I couldn't read that. Please type your question.", **creds)
        return

    # Count usage now that the message is accepted.
    await asyncio.to_thread(record_usage, tenant, is_voice=is_voice)

    log.info("In  %s: %s", sender, user_text)
    source = "voice" if is_voice else "text"
    history = await asyncio.to_thread(recent_history, tid, sender, 12)
    inbound_id = await asyncio.to_thread(log_message, tid, sender, "in", user_text, source=source)
    publish("message", {"wa_user": sender, "direction": "in", "text": user_text,
                        "tenant_id": tid, "source": source})
    publish("typing", {"wa_user": sender, "tenant_id": tid})  # bot is generating a reply

    try:
        ctx: AgentContext = await asyncio.to_thread(run_agent, tenant, sender, user_text, history)
    except LLMUnavailable as e:
        if e.transient:
            # Temporary blip (rate limits / timeouts): ask the user to retry; the
            # message_id of a resend is new, so it won't be deduped away. No staff page.
            log.warning("LLM transiently unavailable for %s: %s", sender, e)
            retry_msg = ("I'm getting a lot of messages right now — please send that again "
                         "in a moment. 🙏")
            await send_text(sender, retry_msg, **creds)
            # Mirror to the conversation log + live feed so it shows in the dashboard like
            # every other outbound (the other error paths log; this one used not to).
            await asyncio.to_thread(log_message, tid, sender, "out", retry_msg, "error", False)
            publish("message", {"wa_user": sender, "direction": "out", "text": retry_msg,
                                "intent": "error", "tenant_id": tid})
        else:
            # Sustained outage / misconfig: own the failure and bring in a human.
            log.error("LLM unavailable (hard) for %s: %s", sender, e)
            await send_text(sender,
                            "Sorry, we're having a technical issue. A staff member will follow "
                            "up with you shortly.", **creds)
            await asyncio.to_thread(log_message, tid, sender, "out", "[llm unavailable]", "error", True)
            await asyncio.to_thread(incidents.record, "llm", "All LLM providers unavailable",
                                    detail=str(e), tenant_id=tid, wa_user=sender)
            await notify.notify_tech(f"[LLM DOWN] +{sender}\nUser: {user_text}\nDetail: {e}")
        publish("stoptyping", {"wa_user": sender, "tenant_id": tid})
        return
    except Exception as ex:
        log.exception("Agent failed for %s", sender)
        await send_text(sender,
                        "Sorry, we're having a temporary issue. A staff member will follow up shortly.",
                        **creds)
        await asyncio.to_thread(log_message, tid, sender, "out", "[agent error]",
                                "error", True)
        await asyncio.to_thread(incidents.record, "agent", "Agent crashed handling a message",
                                detail=repr(ex), tenant_id=tid, wa_user=sender)
        await notify.notify_tech(f"[AGENT ERROR] +{sender}\nUser: {user_text}")
        publish("stoptyping", {"wa_user": sender, "tenant_id": tid})
        return

    # The reply guard blocked a booking confirmation the DB couldn't back — page staff.
    if getattr(ctx, "guard_tripped", False):
        await asyncio.to_thread(incidents.record, "booking",
                                "Blocked an unbacked booking confirmation before it reached the patient",
                                detail=f"User: {user_text}", level="warning",
                                tenant_id=tid, wa_user=sender)
        guard_msg = (f"[BOOKING UNCONFIRMED] +{sender}\nUser: {user_text}\n"
                     "The assistant tried to confirm a booking with no matching "
                     "appointment in the system. Please follow up.")
        await notify.notify_clinic(tenant, guard_msg, kind="escalation")
        await notify.notify_tech(guard_msg)

    # Mirror modality: if the patient sent a voice note, reply with one (gated; falls
    # back to text on any TTS/send failure so the answer is never dropped).
    spoke = await voice_reply.maybe_send(sender, ctx.reply, tenant, creds,
                                         inbound_is_voice=is_voice)
    if not spoke:
        await send_text(sender, ctx.reply, **creds)
    log.info("Out %s (%s): %s", sender, "voice" if spoke else "text", ctx.reply)
    intent = ctx.derived_intent()
    await asyncio.to_thread(log_message, tid, sender, "out", ctx.reply,
                            intent, ctx.needs_human)
    # Tag the inbound (voice or text) note with the turn's intent — analytics on what
    # patients actually ask, including voice notes.
    await asyncio.to_thread(set_message_intent, inbound_id, intent)
    publish("stoptyping", {"wa_user": sender, "tenant_id": tid})
    publish("message", {"wa_user": sender, "direction": "out", "text": ctx.reply,
                        "intent": ctx.derived_intent(), "needs_human": ctx.needs_human,
                        "tenant_id": tid})

    if ctx.needs_human:
        flag = "EMERGENCY" if ctx.emergency else "HANDOVER"
        summary = ""
        try:  # an AI summary so staff don't have to read the whole thread
            from app import analysis
            row = await asyncio.to_thread(analysis.get_or_build, tid, sender)
            summary = analysis.staff_summary_line(row)
        except Exception:  # noqa: BLE001 — summary is best-effort
            log.warning("handover summary build failed for %s", sender)
        msg = (f"[{flag}] +{sender}\nReason: {ctx.escalation_reason}\n"
               f"User: {user_text}\nAI: {ctx.reply}")
        if summary:
            msg += f"\n--- AI summary ---\n{summary}"
        # Patient escalation → the clinic's own staff/owner only. The platform admin is
        # paged for technical issues, not patient handovers.
        await notify.notify_clinic(tenant, msg, kind="escalation")
        publish_notify(f"{'Emergency' if ctx.emergency else 'Handover'} · +{sender}",
                       ctx.escalation_reason or summary or user_text,
                       level="error" if ctx.emergency else "warning", category="handover",
                       tenant_id=tid, wa_user=sender, link=f"/conversations/{sender}")
    elif ctx.booked_ids or ctx.changed_ids:
        # New booking → the clinic's own staff/owner (not the platform admin).
        await notify.notify_clinic(tenant, f"[BOOKING] +{sender}\n" + "\n".join(ctx.actions),
                                   kind="escalation")
        publish_notify(f"New booking · +{sender}", "\n".join(ctx.actions),
                       level="success", category="booking", tenant_id=tid, wa_user=sender,
                       link=f"/conversations/{sender}")


@router.post("/connector/{tenant_id}/webhook")
async def connector_webhook(request: Request, tenant_id: int):
    """Inbound sync: the tenant's external system POSTs appointment changes here so our
    mirror stays accurate. Auth = the connector's webhook_secret via X-Connector-Token."""
    raw = await request.body()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="invalid JSON")
    tenant = await asyncio.to_thread(get_tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")
    conn = (tenant.get("clinic_data") or {}).get("connector") or {}
    secret = conn.get("webhook_secret")
    token = request.headers.get("x-connector-token", "")
    if not secret or not hmac.compare_digest(str(secret), token):
        raise HTTPException(status_code=401, detail="invalid connector token")
    # Idempotency: skip events we've already applied (reuses the dedup table).
    eid = payload.get("event_id")
    if eid and not await asyncio.to_thread(claim_message_id, f"conn:{tenant_id}:{eid}"):
        return {"status": "duplicate"}
    result = await asyncio.to_thread(connectors.apply_inbound_event, tenant_id, payload)
    log.info("connector webhook tenant=%s event=%s -> %s", tenant_id,
             payload.get("event"), result)
    return {"status": result}
