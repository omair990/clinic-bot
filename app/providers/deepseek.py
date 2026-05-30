from app.config import DEEPSEEK_API_KEY, DEEPSEEK_MODEL
from app.llm import LLMResult, Msg, ToolSpec
from app.providers import _openai_compat as _oai

NAME = "deepseek"
MODEL = DEEPSEEK_MODEL
ENDPOINT = "https://api.deepseek.com/chat/completions"
ENABLED = bool(DEEPSEEK_API_KEY)

is_transient = _oai.is_transient
is_rate_limit = _oai.is_rate_limit


def generate(system: str, messages: list[Msg], tools: list[ToolSpec]) -> LLMResult:
    return _oai.generate(NAME, ENDPOINT, MODEL, DEEPSEEK_API_KEY, system, messages, tools)
