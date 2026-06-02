"""Unit tests for conversation analysis (summary + lead scoring) — no DB/network."""
import json

from app import analysis
from app.llm import LLMResult, LLMUnavailable


def test_extract_json_plain():
    assert analysis._extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced_and_prose():
    assert analysis._extract_json('```json\n{"a": 1}\n```')["a"] == 1
    assert analysis._extract_json('Sure! {"a": 1, "b": "x"} done.')["b"] == "x"


def test_extract_json_rejects_non_object_and_garbage():
    assert analysis._extract_json("no json here") is None
    assert analysis._extract_json("") is None
    assert analysis._extract_json("[1, 2, 3]") is None


def test_band_for_score_thresholds():
    assert analysis._band_for_score(70) == "hot"
    assert analysis._band_for_score(40) == "warm"
    assert analysis._band_for_score(39) == "cold"


def test_heuristic_hot_when_booked():
    d = analysis.heuristic_analysis([], "Sara", has_booking=True, inbound_count=1)
    assert d["lead_band"] == "hot" and d["lead_score"] == 85


def test_heuristic_warm_when_engaged():
    thread = [{"direction": "out", "message": "slots?", "intent": "appointment"}]
    assert analysis.heuristic_analysis(thread, None, False, 1)["lead_band"] == "warm"


def test_heuristic_cold_when_quiet():
    thread = [{"direction": "in", "message": "hi", "intent": None}]
    assert analysis.heuristic_analysis(thread, None, False, 1)["lead_band"] == "cold"


def test_normalize_clamps_score_and_fixes_enums():
    fb = analysis.heuristic_analysis([], None, False, 1)   # cold/low baseline
    out = analysis._normalize(
        {"urgency": "BOGUS", "sentiment": "negative", "lead_score": 150,
         "lead_band": "nope", "customer_name": "  Ali  "}, fb)
    assert out["sentiment"] == "negative"
    assert out["urgency"] == "low"        # invalid -> kept the safe fallback
    assert out["lead_score"] == 100       # clamped
    assert out["lead_band"] == "hot"      # invalid band -> derived from the (clamped) score
    assert out["customer_name"] == "Ali"  # trimmed


def test_analyze_conversation_uses_llm(monkeypatch):
    payload = {"customer_name": "Sara", "requested_service": "Dental Cleaning",
               "appointment_preference": "tomorrow evening", "insurance": "Bupa",
               "urgency": "high", "sentiment": "positive", "next_action": "Offer the 6pm slot",
               "lead_band": "hot", "lead_score": 90, "lead_rationale": "ready to book"}
    monkeypatch.setattr(analysis, "_ai_analysis_enabled", lambda: True)
    monkeypatch.setattr(analysis, "generate",
                        lambda s, m, t: LLMResult(text=json.dumps(payload)))
    thread = [{"direction": "in", "message": "cleaning tmrw evening?", "intent": None}]
    data, src = analysis.analyze_conversation(thread, "Sara", False, 1)
    assert src == "ai"
    assert data["lead_band"] == "hot" and data["requested_service"] == "Dental Cleaning"
    assert data["urgency"] == "high" and data["sentiment"] == "positive"
    assert data["insurance"] == "Bupa"


def test_analyze_conversation_off_uses_heuristic_without_llm(monkeypatch):
    # Default (PATIENT_AI_ANALYSIS off) → free heuristic, never calls the LLM.
    monkeypatch.setattr(analysis, "_ai_analysis_enabled", lambda: False)
    def must_not_call(*a, **k):
        raise AssertionError("LLM must not be called when AI analysis is off")
    monkeypatch.setattr(analysis, "generate", must_not_call)
    thread = [{"direction": "in", "message": "book me tomorrow", "intent": None}]
    _data, src = analysis.analyze_conversation(thread, "Sara", True, 2)
    assert src == "heuristic"


def test_staff_summary_line_formats_and_skips_empties():
    a = {"customer_name": "Sara", "requested_service": "Dermatology",
         "appointment_preference": "Thursday evening", "insurance": "Bupa",
         "urgency": "high", "sentiment": None, "next_action": "Call back"}
    s = analysis.staff_summary_line(a)
    assert "Customer: Sara" in s and "Insurance: Bupa" in s and "Urgency: high" in s
    assert "Sentiment" not in s            # empty fields omitted
    assert analysis.staff_summary_line(None) == ""


def test_analyze_conversation_falls_back_when_llm_down(monkeypatch):
    def boom(s, m, t):
        raise LLMUnavailable("all providers down", transient=False)
    monkeypatch.setattr(analysis, "_ai_analysis_enabled", lambda: True)
    monkeypatch.setattr(analysis, "generate", boom)
    thread = [{"direction": "in", "message": "hi", "intent": None}]
    _data, src = analysis.analyze_conversation(thread, None, False, 1)
    assert src == "heuristic"


def test_analyze_conversation_skips_llm_on_empty_thread(monkeypatch):
    def must_not_call(*a, **k):
        raise AssertionError("LLM should not be called for an empty transcript")
    monkeypatch.setattr(analysis, "generate", must_not_call)
    _data, src = analysis.analyze_conversation([], None, False, 0)
    assert src == "heuristic"


def test_analyze_conversation_falls_back_on_unparseable_json(monkeypatch):
    monkeypatch.setattr(analysis, "_ai_analysis_enabled", lambda: True)
    monkeypatch.setattr(analysis, "generate",
                        lambda s, m, t: LLMResult(text="I think this lead is hot!"))
    thread = [{"direction": "in", "message": "book me", "intent": None}]
    _data, src = analysis.analyze_conversation(thread, None, True, 1)
    assert src == "heuristic"   # no JSON -> heuristic (which is 'hot' here anyway)
