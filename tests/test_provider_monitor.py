"""Primary-LLM-provider health monitor: alert once when the primary stays down, all-clear
on recovery. Pure logic — no DB or network (incidents + WhatsApp are stubbed)."""
import asyncio

import pytest

from app import llm, provider_monitor


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    provider_monitor._alerted.clear()
    monkeypatch.setattr(provider_monitor, "AI_PROVIDERS", ["claude", "gemini", "mistral"])
    monkeypatch.setattr(provider_monitor, "LLM_OUTAGE_ALERT_MIN", 30)
    yield
    provider_monitor._alerted.clear()


def _capture(monkeypatch):
    notes, incidents_rec = [], []

    async def fake_notify(text):
        notes.append(text)

    monkeypatch.setattr(provider_monitor, "_notify_admin", fake_notify)
    monkeypatch.setattr(provider_monitor.incidents, "record",
                        lambda *a, **k: incidents_rec.append((a, k)))
    return notes, incidents_rec


def _outage(monkeypatch, value):
    monkeypatch.setattr(llm, "provider_outage_seconds", lambda name: value)


def test_no_alert_when_healthy(monkeypatch):
    notes, inc = _capture(monkeypatch)
    _outage(monkeypatch, None)
    asyncio.run(provider_monitor.check())
    assert notes == [] and inc == []


def test_no_alert_below_threshold(monkeypatch):
    notes, inc = _capture(monkeypatch)
    _outage(monkeypatch, 10 * 60)   # 10 min < 30
    asyncio.run(provider_monitor.check())
    assert notes == [] and inc == []


def test_alerts_once_over_threshold(monkeypatch):
    notes, inc = _capture(monkeypatch)
    _outage(monkeypatch, 35 * 60)   # 35 min >= 30
    asyncio.run(provider_monitor.check())
    asyncio.run(provider_monitor.check())   # second tick must NOT re-alert (dedup)
    assert len(notes) == 1 and len(inc) == 1
    assert "claude" in notes[0] and "fallback" in notes[0].lower()


def test_all_clear_on_recovery(monkeypatch):
    notes, inc = _capture(monkeypatch)
    seq = iter([35 * 60, None])     # down past threshold, then recovered
    monkeypatch.setattr(llm, "provider_outage_seconds", lambda name: next(seq))
    asyncio.run(provider_monitor.check())   # alert
    asyncio.run(provider_monitor.check())   # recovery → all-clear
    assert len(notes) == 2 and "responding again" in notes[1]
    assert "claude" not in provider_monitor._alerted


def test_no_alert_without_admin_number(monkeypatch):
    # _notify_admin is a no-op without ADMIN_WA_NUMBER, but an incident is still recorded.
    monkeypatch.setattr(provider_monitor, "ADMIN_WA_NUMBER", "")
    inc = []
    monkeypatch.setattr(provider_monitor.incidents, "record",
                        lambda *a, **k: inc.append((a, k)))
    _outage(monkeypatch, 40 * 60)
    asyncio.run(provider_monitor.check())
    assert len(inc) == 1   # incident recorded even when no WhatsApp recipient is configured
