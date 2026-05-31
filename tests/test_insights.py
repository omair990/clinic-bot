"""Unit tests for business-insights narrative + windowing — no DB/network."""
from datetime import datetime

from app import insights
from app.config import TZ
from app.llm import LLMResult, LLMUnavailable


def _metrics():
    return {
        "messages": 14, "inbound": 10, "voice_inbound": 2, "voice_share_pct": 20, "users": 4,
        "top_inquiries": [{"intent": "appointment", "n": 5}, {"intent": "chat", "n": 3}],
        "conversion": {"users_messaged": 4, "users_booked": 2, "conversion_pct": 50},
        "peak_hours": [{"hour": 18, "n": 7}],
        "no_shows": 1, "no_show_reasons": [{"reason": "forgot", "n": 1}],
        "lead_mix": {"hot": 1, "warm": 2, "cold": 1}, "missed_opportunities": 1,
    }


def test_window_day_and_week():
    now = datetime(2026, 6, 10, 15, 30, tzinfo=TZ)
    since, until, label = insights.window("day", now)
    assert since.hour == 0 and since.minute == 0 and until == now and label == "Today"
    s2, u2, label2 = insights.window("week", now)
    assert (now - s2).days == 7 and u2 == now and label2 == "Last 7 days"


def test_window_defaults_unknown_period_to_day():
    now = datetime(2026, 6, 10, 9, 0, tzinfo=TZ)
    _s, _u, label = insights.window("garbage", now)
    assert label == "Today"


def test_fallback_narrative_mentions_key_numbers():
    text = insights._fallback_narrative(_metrics(), "Today")
    assert "10 inbound" in text
    assert "50% conversion" in text
    assert "18:00" in text          # busiest hour surfaced


def test_narrative_prefers_llm(monkeypatch):
    monkeypatch.setattr(insights, "generate",
                        lambda s, m, t: LLMResult(text="Strong day; push the warm leads."))
    text, src = insights.narrative(_metrics(), "Today")
    assert src == "ai" and "warm leads" in text


def test_narrative_falls_back_when_llm_down(monkeypatch):
    def boom(s, m, t):
        raise LLMUnavailable("down", transient=False)
    monkeypatch.setattr(insights, "generate", boom)
    text, src = insights.narrative(_metrics(), "Today")
    assert src == "heuristic" and "inbound" in text


def test_narrative_falls_back_on_empty_llm_text(monkeypatch):
    monkeypatch.setattr(insights, "generate", lambda s, m, t: LLMResult(text="   "))
    _text, src = insights.narrative(_metrics(), "Today")
    assert src == "heuristic"
