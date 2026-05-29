import json
import logging

import httpx
from pydantic import ValidationError

from app.config import DEEPSEEK_API_KEY
from app.schema import AIResponse, SYSTEM_PROMPT

log = logging.getLogger(__name__)

NAME = "deepseek"
MODEL = "deepseek-chat"
ENDPOINT = "https://api.deepseek.com/chat/completions"


def _history_to_messages(history: list[dict]) -> list[dict]:
    out = []
    for h in history:
        role = "user" if h["direction"] == "in" else "assistant"
        out.append({"role": role, "content": h["message"]})
    return out


def is_transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or code >= 500
    if isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout)):
        return True
    return False


def call(user_message: str, history: list[dict]) -> AIResponse:
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY not configured")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(_history_to_messages(history))
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": 2048,
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
    }
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=30.0) as client:
        r = client.post(ENDPOINT, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()

    usage = data.get("usage", {})
    log.info("[deepseek] in=%s out=%s", usage.get("prompt_tokens"), usage.get("completion_tokens"))

    content = data["choices"][0]["message"]["content"]
    try:
        return AIResponse.model_validate_json(content)
    except (json.JSONDecodeError, ValidationError) as e:
        raise RuntimeError(f"DeepSeek returned invalid output: {content!r}") from e
