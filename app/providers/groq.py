from app.config import GROQ_API_KEY
from app.llm import LLMResult, Msg, ToolSpec
from app.providers import _openai_compat as _oai

NAME = "groq"
MODEL = "llama-3.3-70b-versatile"
ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

is_transient = _oai.is_transient


def generate(system: str, messages: list[Msg], tools: list[ToolSpec]) -> LLMResult:
    return _oai.generate(NAME, ENDPOINT, MODEL, GROQ_API_KEY, system, messages, tools)
