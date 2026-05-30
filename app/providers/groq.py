from app.config import GROQ_API_KEY, GROQ_MODEL
from app.llm import LLMResult, Msg, ToolSpec
from app.providers import _openai_compat as _oai

NAME = "groq"
MODEL = GROQ_MODEL
ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
ENABLED = bool(GROQ_API_KEY)

is_transient = _oai.is_transient
is_rate_limit = _oai.is_rate_limit


def generate(system: str, messages: list[Msg], tools: list[ToolSpec]) -> LLMResult:
    return _oai.generate(NAME, ENDPOINT, MODEL, GROQ_API_KEY, system, messages, tools)
