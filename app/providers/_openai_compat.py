"""Shared adapter for OpenAI-compatible chat-completions APIs (Groq, DeepSeek).

Implements tool-calling against the standard `/chat/completions` contract.
"""
import json
import logging

import httpx

from app.llm import LLMResult, Msg, ToolCall, ToolSpec

log = logging.getLogger(__name__)


def is_transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or code >= 500
    return isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout))


def _to_messages(system: str, messages: list[Msg]) -> list[dict]:
    out: list[dict] = [{"role": "system", "content": system}]
    for m in messages:
        if m.role == "tool":
            out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
        elif m.role == "assistant" and m.tool_calls:
            out.append({
                "role": "assistant",
                "content": m.content or None,
                "tool_calls": [{
                    "id": tc.id, "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                } for tc in m.tool_calls],
            })
        else:
            out.append({"role": m.role, "content": m.content})
    return out


def _to_tools(tools: list[ToolSpec]) -> list[dict]:
    return [{"type": "function",
             "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
            for t in tools]


def generate(name: str, endpoint: str, model: str, api_key: str,
             system: str, messages: list[Msg], tools: list[ToolSpec]) -> LLMResult:
    if not api_key:
        raise RuntimeError(f"{name}: API key not configured")

    payload = {
        "model": model,
        "messages": _to_messages(system, messages),
        "tools": _to_tools(tools),
        "tool_choice": "auto",
        "temperature": 0.3,
        "max_tokens": 1500,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=40.0) as client:
        r = client.post(endpoint, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()

    usage = data.get("usage", {})
    log.info("[%s] in=%s out=%s", name, usage.get("prompt_tokens"), usage.get("completion_tokens"))

    msg = data["choices"][0]["message"]
    calls = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function", {})
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        calls.append(ToolCall(id=tc.get("id") or fn.get("name", "call"),
                              name=fn.get("name", ""), arguments=args))
    return LLMResult(text=msg.get("content") or "", tool_calls=calls, usage=usage)
