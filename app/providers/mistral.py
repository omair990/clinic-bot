"""Mistral AI provider (OpenAI-compatible chat completions + tool calling).

Set MISTRAL_MODEL to any tool-calling Mistral model (e.g. 'mistral-small-latest',
'mistral-large-latest'). Disabled until MISTRAL_API_KEY is set.
"""
from app.config import MISTRAL_API_KEY, MISTRAL_MODEL
from app.llm import LLMResult, Msg, ToolSpec
from app.providers import _openai_compat as _oai

NAME = "mistral"
MODEL = MISTRAL_MODEL
ENDPOINT = "https://api.mistral.ai/v1/chat/completions"
ENABLED = bool(MISTRAL_API_KEY)

is_transient = _oai.is_transient
is_rate_limit = _oai.is_rate_limit


def generate(system: str, messages: list[Msg], tools: list[ToolSpec]) -> LLMResult:
    return _oai.generate(NAME, ENDPOINT, MODEL, MISTRAL_API_KEY, system, messages, tools)
