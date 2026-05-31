"""Deep, DB-backed tests for the AI features: conversation analysis caching, lead band in
the conversation list, voice-note source tracking, business-insights aggregates, and the
admin routes end-to-end (LLM stubbed). Requires Postgres; auto-skips otherwise."""
import json
import uuid
from datetime import datetime, timedelta

import pytest

from app import analysis, db, insights
from app.config import TZ
from app.llm import LLMResult


@pytest.fixture(scope="module", autouse=True)
def _db():
    try:
        db.init_db()
        if not db.ping():
            pytest.skip("no database reachable")
    except Exception:
        pytest.skip("no database reachable")


def _tenant():
    sfx = uuid.uuid4().hex[:8]
    return db.create_tenant(f"AI {sfx}", f"ai-{sfx}", f"PNAI{sfx}", None,
                            "Asia/Riyadh", None, {"clinic": {"name": "AI"}})


def _user():
    return "9665" + uuid.uuid4().hex[:7]


def _stub_llm(monkeypatch, payload: dict):
    monkeypatch.setattr(analysis, "generate", lambda s, m, t: LLMResult(text=json.dumps(payload)))


# --- Phase 1: voice-note source tracking ---

def test_voice_source_is_stored_and_counted():
    tid, user = _tenant(), _user()
    db.log_message(tid, user, "in", "I'd like to book", source="voice")
    db.log_message(tid, user, "in", "tomorrow please", source="text")
    thread = db.conversation_thread(user, tenant_id=tid)
    assert [m["source"] for m in thread] == ["voice", "text"]
    now = datetime.now(TZ)
    stats = db.insight_message_stats(tid, now - timedelta(hours=1), now + timedelta(minutes=1))
    assert stats["inbound"] == 2 and stats["voice_inbound"] == 1


# --- Phases 2 & 3: conversation analysis caching + lead band ---

def test_get_or_build_caches_and_rebuilds_on_new_messages(monkeypatch):
    tid, user = _tenant(), _user()
    db.log_message(tid, user, "in", "I want a dental cleaning tomorrow evening")
    _stub_llm(monkeypatch, {"customer_name": "Sara", "requested_service": "Dental Cleaning",
                            "appointment_preference": "tomorrow evening", "urgency": "high",
                            "sentiment": "positive", "next_action": "Offer 6pm",
                            "lead_band": "hot", "lead_score": 88, "lead_rationale": "ready"})
    a1 = analysis.get_or_build(tid, user)
    assert a1["lead_band"] == "hot" and a1["source"] == "ai"
    assert a1["requested_service"] == "Dental Cleaning" and a1["message_count"] == 1

    # No new messages -> cached row returned unchanged (no rebuild).
    calls = {"n": 0}
    monkeypatch.setattr(analysis, "generate",
                        lambda *a, **k: calls.__setitem__("n", calls["n"] + 1) or LLMResult(text="{}"))
    a2 = analysis.get_or_build(tid, user)
    assert calls["n"] == 0 and a2["updated_at"] == a1["updated_at"]

    # A new message invalidates the cache and triggers a rebuild.
    db.log_message(tid, user, "out", "Sure! 6pm works.", intent="appointment")
    _stub_llm(monkeypatch, {"lead_band": "warm", "lead_score": 55, "next_action": "confirm"})
    a3 = analysis.get_or_build(tid, user)
    assert a3["message_count"] == 2 and a3["lead_band"] == "warm"


def test_lead_band_shows_in_conversation_list(monkeypatch):
    tid, user = _tenant(), _user()
    db.log_message(tid, user, "in", "hello")
    _stub_llm(monkeypatch, {"lead_band": "hot", "lead_score": 90, "next_action": "book"})
    analysis.get_or_build(tid, user)
    row = next(r for r in db.list_conversations(tenant_id=tid) if r["wa_user"] == user)
    assert row["lead_band"] == "hot"


def test_analysis_heuristic_when_llm_unavailable(monkeypatch):
    from app.llm import LLMUnavailable
    tid, user = _tenant(), _user()
    db.log_message(tid, user, "in", "hi there")
    db.log_message(tid, user, "in", "are you open")
    db.log_message(tid, user, "out", "Yes!", intent="appointment")

    def boom(*a, **k):
        raise LLMUnavailable("down", transient=False)
    monkeypatch.setattr(analysis, "generate", boom)
    a = analysis.get_or_build(tid, user)
    assert a["source"] == "heuristic" and a["lead_band"] in ("hot", "warm", "cold")


# --- Phase 5: business-insights aggregates ---

def test_compute_metrics_is_accurate(monkeypatch):
    tid = _tenant()
    u1, u2 = _user(), _user()
    now = datetime.now(TZ)
    # u1: voice + text inbound, an appointment-intent reply, and a booking
    db.log_message(tid, u1, "in", "voice note", source="voice")
    db.log_message(tid, u1, "in", "follow up", source="text")
    db.log_message(tid, u1, "out", "Booked!", intent="appointment")
    db.create_appointment(tid, u1, "U1", "+1", "Dr. Test", "Consult",
                          now + timedelta(days=1), now + timedelta(days=1, minutes=30))
    # u2: one text inbound + a chat reply, no booking
    db.log_message(tid, u2, "in", "just asking", source="text")
    db.log_message(tid, u2, "out", "Sure", intent="chat")
    # a lead snapshot so the lead mix is non-zero
    db.upsert_conversation_analysis(tid, u1, {"lead_band": "hot", "lead_score": 90}, 3)

    since, until, _ = insights.window("day", now)
    until = now + timedelta(minutes=1)   # include rows just inserted at ~now
    m = insights.compute_metrics(tid, since, until)

    assert m["inbound"] == 3 and m["voice_inbound"] == 1 and m["voice_share_pct"] == 33
    assert m["users"] == 2
    intents = {r["intent"]: r["n"] for r in m["top_inquiries"]}
    assert intents.get("appointment") == 1 and intents.get("chat") == 1
    assert m["conversion"] == {"users_messaged": 2, "users_booked": 1, "conversion_pct": 50}
    assert m["lead_mix"]["hot"] == 1
    assert m["peak_hours"] and m["peak_hours"][0]["n"] >= 1


# --- Admin routes end-to-end (LLM stubbed) ---

def _super_client():
    from fastapi.testclient import TestClient
    from app.config import ADMIN_PASSWORD
    import main
    c = TestClient(main.app)
    r = c.post("/admin/login", data={"username": "", "password": ADMIN_PASSWORD},
               follow_redirects=False)
    assert r.status_code == 303, "super-admin login failed (check ADMIN_PASSWORD)"
    return c


def test_conversation_page_renders_analysis(monkeypatch):
    tid, user = _tenant(), _user()
    db.log_message(tid, user, "in", "I want to book a cleaning")
    _stub_llm(monkeypatch, {"customer_name": "Sara", "requested_service": "Cleaning",
                            "urgency": "high", "sentiment": "positive",
                            "next_action": "Offer evening slot", "lead_band": "hot",
                            "lead_score": 92, "lead_rationale": "keen"})
    c = _super_client()
    r = c.get(f"/admin/conversations/{user}")
    assert r.status_code == 200
    assert "AI summary" in r.text and "Hot" in r.text and "Offer evening slot" in r.text


def test_insights_page_renders(monkeypatch):
    tid, user = _tenant(), _user()
    db.log_message(tid, user, "in", "hello", source="voice")
    monkeypatch.setattr(insights, "generate",
                        lambda s, m, t: LLMResult(text="Quiet day; nurture leads."))
    c = _super_client()
    r = c.get("/admin/insights?period=week")
    assert r.status_code == 200
    assert "Business Insights" in r.text and "Last 7 days" in r.text


def test_refresh_analysis_route(monkeypatch):
    tid, user = _tenant(), _user()
    db.log_message(tid, user, "in", "hi")
    _stub_llm(monkeypatch, {"lead_band": "warm", "lead_score": 50, "next_action": "follow up"})
    c = _super_client()
    r = c.post(f"/admin/conversations/{user}/analysis/refresh", follow_redirects=False)
    assert r.status_code == 303
    assert db.get_conversation_analysis(tid, user)["lead_band"] == "warm"
