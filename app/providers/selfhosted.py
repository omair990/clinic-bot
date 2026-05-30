"""Self-hosted / "own" model via any OpenAI-compatible server (Ollama, vLLM,
RunPod serverless, etc.).

This is the always-available tail of the fallback chain: it has no per-token credit
to run out of, so the bot still answers when every hosted provider is exhausted.

Configure:
  SELFHOSTED_BASE_URL  e.g. 'http://host:11434/v1' (Ollama) or
                       'https://api.runpod.ai/v2/<endpoint-id>/openai/v1' (RunPod).
                       '/chat/completions' is appended automatically if absent.
  SELFHOSTED_MODEL     the served model id/tag (e.g. 'qwen2.5:14b-instruct').
  SELFHOSTED_API_KEY   optional — keyless servers (a bare Ollama) don't need it.

Stays disabled until SELFHOSTED_BASE_URL is set, so it is safe to ship inert.
"""
from app.config import SELFHOSTED_API_KEY, SELFHOSTED_BASE_URL, SELFHOSTED_MODEL
from app.llm import LLMResult, Msg, ToolSpec
from app.providers import _openai_compat as _oai

NAME = "selfhosted"
MODEL = SELFHOSTED_MODEL
ENABLED = bool(SELFHOSTED_BASE_URL)

_base = SELFHOSTED_BASE_URL.rstrip("/")
ENDPOINT = _base if _base.endswith("/chat/completions") else f"{_base}/chat/completions"

is_transient = _oai.is_transient
is_rate_limit = _oai.is_rate_limit


def generate(system: str, messages: list[Msg], tools: list[ToolSpec]) -> LLMResult:
    # Keyless servers still need *some* bearer token to satisfy the adapter; it's ignored.
    return _oai.generate(NAME, ENDPOINT, MODEL, SELFHOSTED_API_KEY or "sk-noauth",
                         system, messages, tools)
