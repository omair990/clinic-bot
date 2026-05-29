"""Gemini provider with manual (multi-turn) function calling."""
import logging

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.config import GEMINI_API_KEY
from app.llm import LLMResult, Msg, ToolCall, ToolSpec

log = logging.getLogger(__name__)

NAME = "gemini"
MODEL = "gemini-2.5-flash"

_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

_TYPES = {
    "object": types.Type.OBJECT,
    "string": types.Type.STRING,
    "integer": types.Type.INTEGER,
    "number": types.Type.NUMBER,
    "boolean": types.Type.BOOLEAN,
    "array": types.Type.ARRAY,
}


def is_transient(exc: BaseException) -> bool:
    if isinstance(exc, genai_errors.ServerError):
        return True
    if isinstance(exc, genai_errors.ClientError):
        return getattr(exc, "code", None) == 429
    return False


def _schema(node: dict) -> types.Schema:
    t = node.get("type", "string")
    kwargs: dict = {"type": _TYPES.get(t, types.Type.STRING)}
    if node.get("description"):
        kwargs["description"] = node["description"]
    if t == "object":
        props = {k: _schema(v) for k, v in node.get("properties", {}).items()}
        if props:
            kwargs["properties"] = props
        if node.get("required"):
            kwargs["required"] = node["required"]
    if t == "array" and node.get("items"):
        kwargs["items"] = _schema(node["items"])
    return types.Schema(**kwargs)


def _to_tools(tools: list[ToolSpec]) -> list[types.Tool]:
    decls = []
    for t in tools:
        params = None
        if t.parameters.get("properties"):
            params = _schema(t.parameters)
        decls.append(types.FunctionDeclaration(
            name=t.name, description=t.description, parameters=params))
    return [types.Tool(function_declarations=decls)]


def _to_contents(messages: list[Msg]) -> list[types.Content]:
    contents: list[types.Content] = []
    pending_responses: list[types.Part] = []

    def flush() -> None:
        if pending_responses:
            contents.append(types.Content(role="user", parts=list(pending_responses)))
            pending_responses.clear()

    for m in messages:
        if m.role == "tool":
            pending_responses.append(types.Part.from_function_response(
                name=m.name or "tool", response=_as_dict(m.content)))
            continue
        flush()
        if m.role == "assistant":
            parts: list[types.Part] = []
            if m.content:
                parts.append(types.Part(text=m.content))
            for tc in m.tool_calls:
                parts.append(types.Part(function_call=types.FunctionCall(
                    name=tc.name, args=tc.arguments)))
            contents.append(types.Content(role="model", parts=parts))
        else:  # user
            contents.append(types.Content(role="user", parts=[types.Part(text=m.content)]))
    flush()
    return contents


def _as_dict(content: str) -> dict:
    import json
    try:
        obj = json.loads(content)
        return obj if isinstance(obj, dict) else {"result": obj}
    except (json.JSONDecodeError, TypeError):
        return {"result": content}


def generate(system: str, messages: list[Msg], tools: list[ToolSpec]) -> LLMResult:
    if _client is None:
        raise RuntimeError("GEMINI_API_KEY not configured")

    response = _client.models.generate_content(
        model=MODEL,
        contents=_to_contents(messages),
        config=types.GenerateContentConfig(
            system_instruction=system,
            tools=_to_tools(tools),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            temperature=0.3,
            max_output_tokens=1500,
        ),
    )

    if not response.candidates:
        raise RuntimeError(f"Gemini returned no candidates (feedback={response.prompt_feedback})")

    parts = response.candidates[0].content.parts or []
    text_chunks: list[str] = []
    calls: list[ToolCall] = []
    for i, part in enumerate(parts):
        fc = getattr(part, "function_call", None)
        if fc and fc.name:
            calls.append(ToolCall(id=f"{fc.name}-{i}", name=fc.name,
                                  arguments=dict(fc.args or {})))
        elif getattr(part, "text", None):
            text_chunks.append(part.text)

    usage = response.usage_metadata
    log.info("[gemini] in=%s out=%s",
             getattr(usage, "prompt_token_count", "?"),
             getattr(usage, "candidates_token_count", "?"))
    return LLMResult(text="".join(text_chunks), tool_calls=calls)
