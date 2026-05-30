"""Tests for the multi-provider fallback + circuit breaker in app.llm.

These exercise the resilience logic with fake providers, so no network or API keys
are touched.
"""
import pytest

from app import llm
from app.llm import LLMResult, LLMUnavailable


class _Transient(Exception):
    pass


class _Hard(Exception):
    pass


class FakeProvider:
    """A provider whose generate() runs a queue of behaviours (exception or result)."""

    def __init__(self, name, behaviours):
        self.NAME = name
        self._behaviours = list(behaviours)
        self.calls = 0

    def generate(self, system, messages, tools):
        self.calls += 1
        b = self._behaviours.pop(0) if self._behaviours else self._last
        self._last = b
        if isinstance(b, Exception):
            raise b
        return b

    @staticmethod
    def is_transient(exc):
        return isinstance(exc, _Transient)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    """Clear breaker state and silence the retry backoff sleep for every test."""
    llm._breaker.clear()
    monkeypatch.setattr(llm.time, "sleep", lambda *_: None)
    yield
    llm._breaker.clear()


def _install(monkeypatch, *providers):
    monkeypatch.setattr(llm, "_providers", list(providers))


def test_falls_back_to_next_provider(monkeypatch):
    ok = LLMResult(text="hi")
    a = FakeProvider("a", [_Transient(), _Transient()])  # fails both attempts
    b = FakeProvider("b", [ok])
    _install(monkeypatch, a, b)

    assert llm.generate("s", [], []) is ok
    assert a.calls == 2  # original + one retry on transient
    assert b.calls == 1


def test_breaker_opens_and_skips_dead_provider(monkeypatch):
    monkeypatch.setattr(llm, "LLM_BREAKER_THRESHOLD", 2)
    ok = LLMResult(text="ok")
    a = FakeProvider("a", [_Hard(), _Hard(), _Hard()])  # always hard-fails
    b = FakeProvider("b", [ok, ok, ok])
    _install(monkeypatch, a, b)

    # Two turns of hard failures trip a's breaker (threshold=2).
    llm.generate("s", [], [])
    llm.generate("s", [], [])
    calls_before = a.calls
    # Third turn: a's breaker is open, so it must be skipped entirely.
    llm.generate("s", [], [])
    assert a.calls == calls_before  # not called again
    assert b.calls == 3


def test_success_resets_breaker(monkeypatch):
    monkeypatch.setattr(llm, "LLM_BREAKER_THRESHOLD", 2)
    a = FakeProvider("a", [_Hard(), LLMResult(text="recovered")])
    _install(monkeypatch, a)

    with pytest.raises(LLMUnavailable):
        llm.generate("s", [], [])          # 1 hard failure recorded (sole provider)
    assert llm._breaker["a"]["fails"] == 1
    llm.generate("s", [], [])              # success -> breaker reset
    assert "a" not in llm._breaker         # state cleared on success


def test_transient_outage_is_flagged_transient(monkeypatch):
    a = FakeProvider("a", [_Transient(), _Transient()])
    _install(monkeypatch, a)
    with pytest.raises(LLMUnavailable) as ei:
        llm.generate("s", [], [])
    assert ei.value.transient is True


def test_hard_outage_is_not_transient(monkeypatch):
    a = FakeProvider("a", [_Hard()])
    _install(monkeypatch, a)
    with pytest.raises(LLMUnavailable) as ei:
        llm.generate("s", [], [])
    assert ei.value.transient is False


def test_all_breakers_open_is_not_transient(monkeypatch):
    monkeypatch.setattr(llm, "LLM_BREAKER_THRESHOLD", 1)
    a = FakeProvider("a", [_Transient(), _Transient()])
    _install(monkeypatch, a)

    with pytest.raises(LLMUnavailable):
        llm.generate("s", [], [])      # trips breaker (threshold=1)
    a.calls = 0
    with pytest.raises(LLMUnavailable) as ei:
        llm.generate("s", [], [])      # breaker open -> nothing tried
    assert a.calls == 0
    assert ei.value.transient is False  # sustained outage, escalate
