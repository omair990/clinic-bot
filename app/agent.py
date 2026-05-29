"""The agent loop: model ⇄ tools until a final natural-language reply.

Synchronous on purpose — providers use sync HTTP clients and tool handlers hit the DB
pool synchronously. The webhook runs this in a worker thread via `asyncio.to_thread`,
so it never blocks the event loop.
"""
import logging

from app.config import AGENT_MAX_STEPS
from app.llm import Msg, generate
from app.prompts import build_system_prompt
from app.tools import TOOL_SPECS, AgentContext, dispatch

log = logging.getLogger(__name__)

_FALLBACK_REPLY = (
    "Sorry, I'm having trouble with that right now. Let me get a staff member to help you."
)


def _history_to_messages(history: list[dict]) -> list[Msg]:
    msgs: list[Msg] = []
    for h in history:
        role = "user" if h["direction"] == "in" else "assistant"
        text = (h.get("message") or "").strip()
        if text:
            msgs.append(Msg(role=role, content=text))
    return msgs


def run_agent(wa_user: str, user_text: str, history: list[dict]) -> AgentContext:
    """Drive one user turn to completion. `history` is prior turns (oldest first),
    excluding the current message."""
    ctx = AgentContext(wa_user=wa_user)
    system = build_system_prompt()
    messages = _history_to_messages(history)
    messages.append(Msg(role="user", content=user_text))

    for step in range(AGENT_MAX_STEPS):
        result = generate(system, messages, TOOL_SPECS)

        if not result.tool_calls:
            ctx.reply = (result.text or "").strip() or _FALLBACK_REPLY
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
        ctx.reply = _FALLBACK_REPLY
    return ctx


def _json(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, default=str)
