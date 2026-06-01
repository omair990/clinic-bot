"""The agent loop: model ⇄ tools until a final natural-language reply.

Synchronous on purpose — providers use sync HTTP clients and tool handlers hit the DB
pool synchronously. The webhook runs this in a worker thread via `asyncio.to_thread`,
so it never blocks the event loop.
"""
import logging

from app import db, reply_guard
from app.config import AGENT_MAX_STEPS, CLINIC_DATA
from app.connectors import get_connector
from app.llm import Msg, generate
from app.prompts import build_system_prompt
from app.tools import TOOL_SPECS, AgentContext, dispatch

log = logging.getLogger(__name__)

_FALLBACK_REPLY = (
    "Sorry, I'm having trouble with that right now. Let me get a staff member to help you."
)
_FALLBACK_REPLY_AR = (
    "عذرًا، أواجه مشكلة في ذلك الآن. سأطلب من أحد الموظفين مساعدتك."
)
_LANG_NAME = {"ar": "Arabic", "en": "English"}


def _enforce_language(system: str, messages: list[Msg], user_text: str, reply: str) -> str:
    """Strong language guard: the reply MUST be in the patient's language. The system prompt
    already asks for this, but models occasionally drift — so when the reply clearly answers
    in the wrong language we ask the model, once, to rewrite the SAME answer in the right one.
    We only accept the rewrite if it actually fixes the language; otherwise keep the original."""
    if not reply_guard.language_mismatch(user_text, reply):
        return reply
    want = reply_guard.detect_language(user_text)
    target = _LANG_NAME.get(want)
    if not target:
        return reply
    log.warning("Reply language mismatch (patient=%s) — regenerating in %s", want, target)
    nudge = (
        f"Your previous reply was in the wrong language. The patient wrote in {target}, so you "
        f"MUST answer in {target}. Rewrite your previous answer entirely in {target}, keeping "
        "the same meaning. Keep doctor names, service names and codes exactly as they are. "
        "Output only the message for the patient — nothing else.")
    retry = messages + [
        Msg(role="assistant", content=reply),
        Msg(role="user", content=nudge),
    ]
    try:
        # Keep TOOL_SPECS so the message history (which may carry this turn's tool_use blocks)
        # stays valid; the nudge tells the model to just rewrite, not call tools again.
        result = generate(system, retry, TOOL_SPECS)
    except Exception:  # noqa: BLE001 — a retry failure must never drop the original turn
        log.warning("Language regeneration failed; keeping original reply")
        return reply
    new = (result.text or "").strip()
    if new and not reply_guard.language_mismatch(user_text, new):
        return new
    log.warning("Language regeneration did not resolve the mismatch; keeping original reply")
    return reply


def _history_to_messages(history: list[dict]) -> list[Msg]:
    msgs: list[Msg] = []
    for h in history:
        role = "user" if h["direction"] == "in" else "assistant"
        text = (h.get("message") or "").strip()
        if text:
            msgs.append(Msg(role=role, content=text))
    return msgs


def run_agent(tenant: dict | None, wa_user: str, user_text: str,
              history: list[dict]) -> AgentContext:
    """Drive one user turn to completion for a tenant. `history` is prior turns
    (oldest first), excluding the current message."""
    clinic_data = (tenant or {}).get("clinic_data") or CLINIC_DATA
    tenant_id = (tenant or {}).get("id") or 0
    ctx = AgentContext(wa_user=wa_user, tenant_id=tenant_id, clinic_data=clinic_data,
                       connector=get_connector(tenant))
    known_name = None
    no_show = None
    review = None
    past_visits: list = []
    if tenant_id:
        try:
            known_name = db.get_patient_name(tenant_id, wa_user)
            no_show = db.open_no_show_followup(tenant_id, wa_user)
            review = db.open_review_request(tenant_id, wa_user)
            past_visits = db.recent_appointments_for_user(tenant_id, wa_user)
        except Exception:  # noqa: BLE001 — these lookups must never block a turn
            pass
    ctx.no_show = no_show
    ctx.review = review
    system = build_system_prompt(clinic_data, patient_name=known_name, wa_user=wa_user,
                                 no_show=no_show, history=past_visits, review=review)
    messages = _history_to_messages(history)
    messages.append(Msg(role="user", content=user_text))

    for step in range(AGENT_MAX_STEPS):
        result = generate(system, messages, TOOL_SPECS)

        if not result.tool_calls:
            ctx.reply = ((result.text or "").strip()
                         or reply_guard.localize(user_text, _FALLBACK_REPLY, _FALLBACK_REPLY_AR))
            reply_guard.verify(ctx, user_text)   # never state a booking/time we can't back
            if not ctx.guard_tripped:            # don't re-touch a localized safe message
                ctx.reply = _enforce_language(system, messages, user_text, ctx.reply)
            return ctx

        messages.append(Msg(role="assistant", content=result.text or "",
                            tool_calls=result.tool_calls))
        for call in result.tool_calls:
            output = dispatch(call.name, call.arguments, ctx)
            messages.append(Msg(role="tool", tool_call_id=call.id,
                                name=call.name, content=_json(output)))

    # Exhausted tool budget without a final answer — hand off rather than loop forever.
    log.warning("Agent hit step limit for %s", wa_user)
    ctx.needs_human = True
    if not ctx.reply:
        ctx.reply = reply_guard.localize(user_text, _FALLBACK_REPLY, _FALLBACK_REPLY_AR)
    reply_guard.verify(ctx, user_text)
    return ctx


def _json(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, default=str)
