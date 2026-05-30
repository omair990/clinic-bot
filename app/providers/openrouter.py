"""OpenRouter provider — one key, many models, via the OpenAI-compatible contract.

Set OPENROUTER_MODEL to any tool-calling model OpenRouter exposes
(e.g. 'openai/gpt-4o-mini', 'google/gemini-2.0-flash-001', 'anthropic/claude-3.5-haiku').
"""
from app.config import OPENROUTER_API_KEY, OPENROUTER_MODEL
from app.llm import LLMResult, Msg, ToolSpec
from app.providers import _openai_compat as _oai

NAME = "openrouter"
MODEL = OPENROUTER_MODEL
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
ENABLED = bool(OPENROUTER_API_KEY)

is_transient = _oai.is_transient
is_rate_limit = _oai.is_rate_limit


def generate(system: str, messages: list[Msg], tools: list[ToolSpec]) -> LLMResult:
    return _oai.generate(NAME, ENDPOINT, MODEL, OPENROUTER_API_KEY, system, messages, tools)
