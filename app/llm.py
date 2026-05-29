"""Provider-agnostic LLM layer: normalised message/tool types + multi-provider fallback.

Each provider module exposes:
    NAME: str
    generate(system: str, messages: list[Msg], tools: list[ToolSpec]) -> LLMResult
    is_transient(exc: BaseException) -> bool

The agent loop (app.agent) speaks only in these neutral types; providers convert to
their own wire format at call time. Because the message list stays neutral, we can fall
back to a different provider mid-conversation without losing state.
"""
import importlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.config import AI_PROVIDERS

log = logging.getLogger(__name__)


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict  # JSON Schema object


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class Msg:
    role: str  # "user" | "assistant" | "tool"
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None  # for role == "tool"
    name: str | None = None          # tool name, for role == "tool"


@dataclass
class LLMResult:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)


_providers: list = []
for _name in AI_PROVIDERS:
    try:
        _providers.append(importlib.import_module(f"app.providers.{_name}"))
    except Exception as e:  # noqa: BLE001
        log.error("Failed to load provider %s: %s", _name, e)

if not _providers:
    raise RuntimeError("No AI providers configured. Set AI_PROVIDERS in the environment.")

log.info("LLM providers loaded: %s", [p.NAME for p in _providers])


def generate(system: str, messages: list[Msg], tools: list[ToolSpec]) -> LLMResult:
    """One model turn with cross-provider fallback. Retries transient errors once per
    provider before moving to the next. Raises if every provider fails."""
    last_err: BaseException | None = None
    for provider in _providers:
        for attempt in range(2):
            try:
                return provider.generate(system, messages, tools)
            except Exception as e:  # noqa: BLE001
                last_err = e
                if provider.is_transient(e):
                    if attempt == 0:
                        log.warning("[%s] transient %s — retrying", provider.NAME, type(e).__name__)
                        time.sleep(1.5)
                        continue
                    log.warning("[%s] still failing — falling back", provider.NAME)
                    break
                log.error("[%s] failed: %s", provider.NAME, e)
                break
    raise last_err if last_err else RuntimeError("All LLM providers failed")
