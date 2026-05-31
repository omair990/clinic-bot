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


# --- Gap 1: detected intent stored on the inbound (voice/text) message ---

def test_log_message_returns_id_and_intent_tagging():
    tid, user = _tenant(), _user()
    mid = db.log_message(tid, user, "in", "transcribed voice text", source="voice")
    assert isinstance(mid, int)
    db.set_message_intent(mid, "appointment")
    thread = db.conversation_thread(user, tenant_id=tid)
    assert thread[0]["source"] == "voice" and thread[0]["intent"] == "appointment"


def test_set_message_intent_ignores_blanks():
    tid, user = _tenant(), _user()
    mid = db.log_message(tid, user, "in", "hi")
    db.set_message_intent(mid, None)        # no-op, must not raise
    db.set_message_intent(0, "appointment")  # no id, no-op
    assert db.conversation_thread(user, tenant_id=tid)[0]["intent"] is None


def test_webhook_tags_inbound_message_with_turn_intent(monkeypatch):
    import asyncio
    from app import webhook
    from app.tools import AgentContext
    tid = db.get_default_tenant()["id"]   # webhook resolves None phone -> default tenant
    user = _user()

    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(webhook, "send_text", _noop)
    monkeypatch.setattr(webhook, "mark_read", _noop)
    # Agent classifies this turn as a booking (booked_ids -> derived intent 'appointment').
    monkeypatch.setattr(webhook, "run_agent",
                        lambda tenant, sender, text, hist: AgentContext(
                            wa_user=sender, reply="Booked!", booked_ids=[1]))

    msg = {"from": user, "id": "wamid." + uuid.uuid4().hex,
           "type": "text", "text": {"body": "book me tomorrow"}}
    asyncio.run(webhook._handle_message(msg, None))

    inbound = [m for m in db.conversation_thread(user, tenant_id=tid) if m["direction"] == "in"]
    assert inbound and inbound[0]["intent"] == "appointment"   # tagged after the agent ran


# --- Gap 2: scheduled insights digest delivery ---

def test_claim_digest_is_idempotent_per_day():
    from datetime import date
    tid = _tenant()
    d = date(2026, 6, 1)
    assert db.claim_digest(tid, "day", d) is True      # first claim
    assert db.claim_digest(tid, "day", d) is False     # same day -> already sent
    assert db.claim_digest(tid, "day", date(2026, 6, 2)) is True   # next day -> claimable


def _digest_tenant(owner: str):
    sfx = uuid.uuid4().hex[:8]
    return db.create_tenant(f"Dig {sfx}", f"dig-{sfx}", f"PNDG{sfx}", None, "Asia/Riyadh",
                            None, {"clinic": {"name": "Dig"}, "owner_wa_number": owner})


def test_run_digests_sends_daily_once(monkeypatch):
    import asyncio
    import app.wa_client as wa
    owner = "owner-" + uuid.uuid4().hex[:8]
    tid = _digest_tenant(owner)
    db.log_message(tid, _user(), "in", "hello")
    sent = []

    async def fake_send(to, body, **k):
        sent.append((to, body))
    monkeypatch.setattr(wa, "send_text", fake_send)
    monkeypatch.setattr(insights, "generate", lambda s, m, t: LLMResult(text="ok"))
    monkeypatch.setattr(insights, "INSIGHTS_DIGEST_HOUR", 0)
    monkeypatch.setattr(insights, "INSIGHTS_WEEKLY_DOW", 0)   # Monday
    tuesday = datetime(2026, 6, 2, 10, 0, tzinfo=TZ)          # not Monday -> weekly skipped

    asyncio.run(insights.run_digests(tuesday))
    mine = [b for to, b in sent if to == owner]
    assert len(mine) == 1 and "insights" in mine[0]
    asyncio.run(insights.run_digests(tuesday))               # same day -> no resend
    assert len([b for to, b in sent if to == owner]) == 1


def test_run_digests_includes_weekly_on_dow(monkeypatch):
    import asyncio
    import app.wa_client as wa
    owner = "owner-" + uuid.uuid4().hex[:8]
    tid = _digest_tenant(owner)
    db.log_message(tid, _user(), "in", "hello")
    sent = []

    async def fake_send(to, body, **k):
        sent.append((to, body))
    monkeypatch.setattr(wa, "send_text", fake_send)
    monkeypatch.setattr(insights, "generate", lambda s, m, t: LLMResult(text="ok"))
    monkeypatch.setattr(insights, "INSIGHTS_DIGEST_HOUR", 0)
    monkeypatch.setattr(insights, "INSIGHTS_WEEKLY_DOW", 0)
    monday = datetime(2026, 6, 1, 9, 0, tzinfo=TZ)            # Monday -> day + week both fire
    asyncio.run(insights.run_digests(monday))
    assert len([b for to, b in sent if to == owner]) == 2


def test_run_digests_skips_before_send_hour(monkeypatch):
    import asyncio
    import app.wa_client as wa
    owner = "owner-" + uuid.uuid4().hex[:8]
    _digest_tenant(owner)
    sent = []

    async def fake_send(to, body, **k):
        sent.append((to, body))
    monkeypatch.setattr(wa, "send_text", fake_send)
    monkeypatch.setattr(insights, "INSIGHTS_DIGEST_HOUR", 8)
    early = datetime(2026, 6, 2, 6, 0, tzinfo=TZ)             # 06:00 < 08:00 send hour
    asyncio.run(insights.run_digests(early))
    assert [s for s in sent if s[0] == owner] == []
