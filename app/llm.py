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
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from app.config import AI_PROVIDERS, LLM_BREAKER_COOLDOWN_S, LLM_BREAKER_THRESHOLD

log = logging.getLogger(__name__)


class LLMUnavailable(Exception):
    """No provider could produce a response this turn.

    `transient` distinguishes a temporary blip (rate limits / timeouts — the caller
    should ask the user to retry) from a hard outage (bad config, all breakers open —
    the caller should escalate to a human).
    """

    def __init__(self, message: str, *, transient: bool):
        super().__init__(message)
        self.transient = transient


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


# --- Per-provider circuit breaker (shared across webhook worker threads) ---
_breaker_lock = threading.Lock()
_breaker: dict[str, dict] = {}  # name -> {"fails": int, "open_until": float (monotonic)}


def _breaker_open(name: str, now: float) -> bool:
    with _breaker_lock:
        st = _breaker.get(name)
        return bool(st and now < st["open_until"])


def _record_success(name: str) -> None:
    with _breaker_lock:
        _breaker.pop(name, None)  # reset on any success


def _record_failure(name: str, now: float) -> None:
    with _breaker_lock:
        st = _breaker.setdefault(name, {"fails": 0, "open_until": 0.0})
        st["fails"] += 1
        if st["fails"] >= LLM_BREAKER_THRESHOLD:
            st["open_until"] = now + LLM_BREAKER_COOLDOWN_S
            log.warning("[%s] circuit breaker OPEN for %.0fs after %d consecutive failures",
                        name, LLM_BREAKER_COOLDOWN_S, st["fails"])


def generate(system: str, messages: list[Msg], tools: list[ToolSpec]) -> LLMResult:
    """One model turn with cross-provider fallback.

    Skips providers whose breaker is open, retries transient errors once per provider,
    and trips a provider's breaker after repeated failures. Raises ``LLMUnavailable``
    (with a ``transient`` flag) if no provider produces a result.
    """
    last_err: BaseException | None = None
    tried = 0
    any_hard = False  # a non-transient failure means "don't tell the user to just retry"

    for provider in _providers:
        if _breaker_open(provider.NAME, time.monotonic()):
            log.info("[%s] breaker open — skipping", provider.NAME)
            continue

        tried += 1
        for attempt in range(2):
            try:
                result = provider.generate(system, messages, tools)
                _record_success(provider.NAME)
                return result
            except Exception as e:  # noqa: BLE001
                last_err = e
                transient = provider.is_transient(e)
                if transient and attempt == 0:
                    log.warning("[%s] transient %s — retrying", provider.NAME, type(e).__name__)
                    time.sleep(1.5)
                    continue
                if transient:
                    log.warning("[%s] still failing — falling back", provider.NAME)
                else:
                    any_hard = True
                    log.error("[%s] failed: %s", provider.NAME, e)
                _record_failure(provider.NAME, time.monotonic())
                break

    # transient (ask user to retry) only if we actually tried something and every
    # failure was temporary. Nothing tried (all breakers open) == sustained outage.
    transient_overall = tried > 0 and not any_hard
    raise LLMUnavailable(
        f"All LLM providers exhausted (tried={tried}, hard_failure={any_hard})",
        transient=transient_overall,
    ) from last_err
