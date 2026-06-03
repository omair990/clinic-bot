"""Anthropic Claude provider with tool use + prompt caching.

The tools and system prompt are identical on every call within a conversation, so we
mark the system block with `cache_control` to cache the (tools + system) prefix — cutting
input-token cost on multi-step tool loops and follow-up turns.
"""
import logging

import anthropic

from app.config import ANTHROPIC_API_KEY, CLAUDE_MODEL, LLM_MAX_TOKENS, LLM_STOP, LLM_TIMEOUT_S
from app.llm import LLMResult, Msg, ToolCall, ToolSpec

log = logging.getLogger(__name__)

NAME = "claude"
MODEL = CLAUDE_MODEL
ENABLED = bool(ANTHROPIC_API_KEY)

# Cap the request well below the SDK default (600s) so a hung call can't pin a
# worker thread; the fallback chain takes over instead.
_client = (anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=LLM_TIMEOUT_S)
           if ANTHROPIC_API_KEY else None)


def is_transient(exc: BaseException) -> bool:
    if isinstance(exc, (anthropic.RateLimitError, anthropic.APITimeoutError,
                        anthropic.APIConnectionError, anthropic.InternalServerError)):
        return True
    if isinstance(exc, anthropic.APIStatusError):
        code = getattr(exc, "status_code", 0)
        return code == 429 or code >= 500
    return False


def is_rate_limit(exc: BaseException) -> bool:
    """Rate-limited but alive — retry, but don't trip the circuit breaker."""
    if isinstance(exc, anthropic.RateLimitError):
        return True
    if isinstance(exc, anthropic.APIStatusError):
        return getattr(exc, "status_code", 0) == 429
    return False


def _to_messages(messages: list[Msg]) -> list[dict]:
    out: list[dict] = []
    pending_results: list[dict] = []

    def flush() -> None:
        if pending_results:
            out.append({"role": "user", "content": list(pending_results)})
            pending_results.clear()

    for m in messages:
        if m.role == "tool":
            pending_results.append({
                "type": "tool_result",
                "tool_use_id": m.tool_call_id,
                "content": m.content,
            })
            continue
        flush()
        if m.role == "assistant":
            content: list[dict] = []
            if m.content:
                content.append({"type": "text", "text": m.content})
            for tc in m.tool_calls:
                content.append({"type": "tool_use", "id": tc.id, "name": tc.name,
                                "input": tc.arguments})
            out.append({"role": "assistant", "content": content})
        else:  # user
            out.append({"role": "user", "content": m.content})
    flush()

    # Anthropic requires the first message to be from the user.
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


def _to_tools(tools: list[ToolSpec]) -> list[dict]:
    return [{"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in tools]


def generate(system: str, messages: list[Msg], tools: list[ToolSpec]) -> LLMResult:
    if _client is None:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    resp = _client.messages.create(
        model=MODEL,
        max_tokens=LLM_MAX_TOKENS,
        temperature=0.3,
        stop_sequences=LLM_STOP,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        tools=_to_tools(tools),
        messages=_to_messages(messages),
    )

    text_chunks: list[str] = []
    calls: list[ToolCall] = []
    for block in resp.content:
        if block.type == "text":
            text_chunks.append(block.text)
        elif block.type == "tool_use":
            calls.append(ToolCall(id=block.id, name=block.name, arguments=block.input or {}))

    usage = resp.usage
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    in_tok = (getattr(usage, "input_tokens", 0) or 0) + cache_read   # cache reads billed as input
    out_tok = getattr(usage, "output_tokens", 0) or 0
    log.info("[claude] in=%s out=%s cache_read=%s",
             getattr(usage, "input_tokens", "?"), out_tok, cache_read)
    return LLMResult(text="".join(text_chunks), tool_calls=calls,
                     usage={"input_tokens": in_tok, "output_tokens": out_tok})
