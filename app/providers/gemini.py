import logging

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.config import GEMINI_API_KEY
from app.schema import AIResponse, SYSTEM_PROMPT

log = logging.getLogger(__name__)

NAME = "gemini"
MODEL = "gemini-2.5-flash"

# Transient errors that should trigger fallback to next provider
TransientError = (genai_errors.ServerError, genai_errors.ClientError)

_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


def _history_to_contents(history: list[dict]) -> list[dict]:
    out = []
    for h in history:
        role = "user" if h["direction"] == "in" else "model"
        out.append({"role": role, "parts": [{"text": h["message"]}]})
    return out


def is_transient(exc: BaseException) -> bool:
    if isinstance(exc, genai_errors.ServerError):
        return True
    if isinstance(exc, genai_errors.ClientError) and getattr(exc, "code", None) == 429:
        return True
    return False


def call(user_message: str, history: list[dict]) -> AIResponse:
    if _client is None:
        raise RuntimeError("GEMINI_API_KEY not configured")
    contents = _history_to_contents(history)
    contents.append({"role": "user", "parts": [{"text": user_message}]})

    response = _client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=AIResponse,
            max_output_tokens=2048,
        ),
    )
    usage = response.usage_metadata
    log.info(
        "[gemini] in=%s out=%s",
        getattr(usage, "prompt_token_count", "?"),
        getattr(usage, "candidates_token_count", "?"),
    )
    parsed = response.parsed
    if parsed is None:
        raise RuntimeError(f"Gemini returned unparseable output: {response.text!r}")
    return parsed
