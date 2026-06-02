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

def test_recent_appointments_for_user_orders_newest_first():
    tid, user = _tenant(), _user()
    now = datetime.now(TZ)
    db.create_appointment(tid, user, "P", "+1", "Dr. A", "Consult",
                          now - timedelta(days=10), now - timedelta(days=10) + timedelta(minutes=30))
    db.create_appointment(tid, user, "P", "+1", "Dr. B", "Cleaning",
                          now - timedelta(days=2), now - timedelta(days=2) + timedelta(minutes=30))
    rows = db.recent_appointments_for_user(tid, user)
    assert [r["doctor"] for r in rows] == ["Dr. B", "Dr. A"]


def test_insight_top_doctors_and_sentiment():
    tid = _tenant()
    u1, u2 = _user(), _user()
    now = datetime.now(TZ)
    db.create_appointment(tid, u1, "P", "+1", "Dr. Pop", "Consult",
                          now + timedelta(days=1), now + timedelta(days=1, minutes=30))
    db.create_appointment(tid, u2, "P", "+1", "Dr. Pop", "Consult",
                          now + timedelta(days=1, hours=1), now + timedelta(days=1, hours=1, minutes=30))
    db.upsert_conversation_analysis(tid, u1, {"sentiment": "negative", "lead_band": "warm",
                                              "lead_score": 50}, 1)
    since, _until, _ = insights.window("day", now)
    m = insights.compute_metrics(tid, since, now + timedelta(minutes=1))
    assert m["top_doctors"][0] == {"doctor": "Dr. Pop", "n": 2}
    assert m["sentiment"]["negative"] == 1


def test_review_request_capture_and_stats():
    from app.tools import AgentContext, dispatch
    tid, user = _tenant(), _user()
    now = datetime.now(TZ)
    appt = db.create_appointment(tid, user, "P", "+1", "Dr. R", "Consult",
                                 now - timedelta(days=1), now - timedelta(days=1) + timedelta(minutes=30))
    assert db.create_review_request(tid, appt["id"], user) is not None
    assert db.create_review_request(tid, appt["id"], user) is None   # idempotent
    pend = db.open_review_request(tid, user)
    assert pend and pend["appointment_id"] == appt["id"]
    ctx = AgentContext(wa_user=user, tenant_id=tid, clinic_data={}, review=pend)
    out = dispatch("record_review", {"appointment_id": appt["id"], "rating": 5,
                                     "comment": "great service"}, ctx)
    assert out["recorded"] and out["rating"] == 5
    assert db.open_review_request(tid, user) is None    # resolved
    st = db.review_stats(tid)
    assert st["responded"] == 1 and st["avg_rating"] == 5.0


def test_record_review_rejects_out_of_range_rating():
    from app.tools import AgentContext, dispatch
    tid, user = _tenant(), _user()
    now = datetime.now(TZ)
    appt = db.create_appointment(tid, user, "P", "+1", "Dr. R", "Consult",
                                 now - timedelta(days=1), now - timedelta(days=1) + timedelta(minutes=30))
    db.create_review_request(tid, appt["id"], user)
    ctx = AgentContext(wa_user=user, tenant_id=tid, clinic_data={},
                       review=db.open_review_request(tid, user))
    assert dispatch("record_review", {"appointment_id": appt["id"], "rating": 9}, ctx)["error"] == "bad_rating"


def test_completion_opens_review_request(monkeypatch):
    import app.notifications as notif
    tid, user = _tenant(), _user()
    appt = _make_appt(tid, user)
    sent = []

    async def fake_send(to, body, **k):
        sent.append(body)
    monkeypatch.setattr(notif, "send_text", fake_send)
    c = _super_client()
    c.post(f"/api/appointments/{appt['id']}/status",
           json={"status": "completed"}, follow_redirects=False)
    assert any("rating from 1 to 5" in b for b in sent)      # review ask sent
    assert db.open_review_request(tid, user) is not None      # request opened


def test_reviews_api_returns_rows_and_stats():
    c = _super_client()
    r = c.get("/api/reviews")
    assert r.status_code == 200 and "rows" in r.json() and "stats" in r.json()


def test_conversation_thread_returns_most_recent_in_chronological_order():
    tid, user = _tenant(), _user()
    for i in range(5):
        db.log_message(tid, user, "in", f"msg{i}")
    rows = db.conversation_thread(user, limit=3, tenant_id=tid)
    # newest 3 messages, displayed oldest-first (not the oldest 3)
    assert [r["message"] for r in rows] == ["msg2", "msg3", "msg4"]


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
    r = c.post("/api/login", json={"username": "", "password": ADMIN_PASSWORD})
    assert r.status_code == 200, "super-admin login failed (check ADMIN_PASSWORD)"
    return c


def test_conversation_page_renders_analysis(monkeypatch):
    tid, user = _tenant(), _user()
    db.log_message(tid, user, "in", "I want to book a cleaning")
    _stub_llm(monkeypatch, {"customer_name": "Sara", "requested_service": "Cleaning",
                            "urgency": "high", "sentiment": "positive",
                            "next_action": "Offer evening slot", "lead_band": "hot",
                            "lead_score": 92, "lead_rationale": "keen"})
    c = _super_client()
    r = c.get(f"/api/conversations/{user}")
    assert r.status_code == 200
    a = r.json()["analysis"]
    assert a["lead_band"] == "hot" and a["next_action"] == "Offer evening slot"


def test_insights_page_renders(monkeypatch):
    tid, user = _tenant(), _user()
    db.log_message(tid, user, "in", "hello", source="voice")
    monkeypatch.setattr(insights, "generate",
                        lambda s, m, t: LLMResult(text="Quiet day; nurture leads."))
    c = _super_client()
    r = c.get("/api/insights?period=week")
    assert r.status_code == 200
    assert r.json()["report"]["period"] == "week" and "metrics" in r.json()["report"]


def test_refresh_analysis_route(monkeypatch):
    tid, user = _tenant(), _user()
    db.log_message(tid, user, "in", "hi")
    _stub_llm(monkeypatch, {"lead_band": "warm", "lead_score": 50, "next_action": "follow up"})
    c = _super_client()
    r = c.post(f"/api/conversations/{user}/analysis/refresh")
    assert r.status_code == 200
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
    # digest_frequency "both" opts this clinic into daily + weekly (default is off).
    return db.create_tenant(f"Dig {sfx}", f"dig-{sfx}", f"PNDG{sfx}", None, "Asia/Riyadh",
                            None, {"clinic": {"name": "Dig"}, "owner_wa_number": owner,
                                   "notifications": {"digest_frequency": "both"}})


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


def test_run_digests_skips_clinic_with_digest_off(monkeypatch):
    import asyncio
    import app.wa_client as wa
    # A clinic with a digest recipient but no digest_frequency (default "off") gets nothing.
    owner = "owner-" + uuid.uuid4().hex[:8]
    sfx = uuid.uuid4().hex[:8]
    db.create_tenant(f"Off {sfx}", f"off-{sfx}", f"PNOFF{sfx}", None, "Asia/Riyadh", None,
                     {"clinic": {"name": "Off"}, "owner_wa_number": owner})  # no notifications.digest_frequency
    sent = []
    monkeypatch.setattr(wa, "send_text", lambda to, body, **k: sent.append(to))
    monkeypatch.setattr(insights, "generate", lambda s, m, t: LLMResult(text="ok"))
    monkeypatch.setattr(insights, "INSIGHTS_DIGEST_HOUR", 0)
    asyncio.run(insights.run_digests(datetime(2026, 6, 2, 10, 0, tzinfo=TZ)))
    assert owner not in sent


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


def _make_appt(tid, user):
    now = datetime.now(TZ)
    return db.create_appointment(tid, user, "Patient", "+1", "Dr. N", "Consult",
                                 now + timedelta(days=2), now + timedelta(days=2, minutes=30))


def test_dashboard_cancel_notifies_patient(monkeypatch):
    import app.notifications as notif
    tid, user = _tenant(), _user()
    appt = _make_appt(tid, user)
    sent = []

    async def fake_send(to, body, **k):
        sent.append((to, body))
    monkeypatch.setattr(notif, "send_text", fake_send)

    c = _super_client()
    r = c.post(f"/api/appointments/{appt['id']}/status", json={"status": "cancelled"})
    assert r.status_code == 200
    assert db.get_appointment_by_id(appt["id"])["status"] == "cancelled"
    assert any(to == user and "cancelled" in body for to, body in sent)
    conv = db.conversation_thread(user, tenant_id=tid)
    assert any(m["direction"] == "out" and "cancelled" in m["message"]
               and m["intent"] == "appointment" for m in conv)


def test_dashboard_complete_notifies_patient(monkeypatch):
    import app.notifications as notif
    tid, user = _tenant(), _user()
    appt = _make_appt(tid, user)
    sent = []

    async def fake_send(to, body, **k):
        sent.append((to, body))
    monkeypatch.setattr(notif, "send_text", fake_send)

    c = _super_client()
    c.post(f"/api/appointments/{appt['id']}/status",
           json={"status": "completed"}, follow_redirects=False)
    assert any(to == user and "Thank you" in body for to, body in sent)


def test_no_show_status_does_not_notify(monkeypatch):
    import app.notifications as notif
    tid, user = _tenant(), _user()
    appt = _make_appt(tid, user)
    sent = []

    async def fake_send(to, body, **k):
        sent.append((to, body))
    monkeypatch.setattr(notif, "send_text", fake_send)

    c = _super_client()
    c.post(f"/api/appointments/{appt['id']}/status",
           json={"status": "no_show"}, follow_redirects=False)
    assert sent == []   # only cancel/complete notify


def test_repeat_cancel_does_not_double_notify(monkeypatch):
    import app.notifications as notif
    tid, user = _tenant(), _user()
    appt = _make_appt(tid, user)
    sent = []

    async def fake_send(to, body, **k):
        sent.append((to, body))
    monkeypatch.setattr(notif, "send_text", fake_send)

    c = _super_client()
    c.post(f"/api/appointments/{appt['id']}/status",
           json={"status": "cancelled"}, follow_redirects=False)
    c.post(f"/api/appointments/{appt['id']}/status",   # already cancelled -> no send
           json={"status": "cancelled"}, follow_redirects=False)
    assert len([s for s in sent if s[0] == user]) == 1


def test_handover_notifies_staff_with_ai_summary(monkeypatch):
    import asyncio
    from app import webhook, analysis
    from app.tools import AgentContext
    tid = db.get_default_tenant()["id"]
    user = _user()
    sent = []

    async def fake_send(to, body, **k):
        sent.append((to, body))

    async def fake_mark(*a, **k):
        return None

    from app import settings, wa_client, notify
    monkeypatch.setattr(settings, "get",
                        lambda key, default=None: "999admin" if key == "ADMIN_WA_NUMBER" else default)
    monkeypatch.setattr(webhook, "send_text", fake_send)       # patient reply
    monkeypatch.setattr(wa_client, "send_text", fake_send)     # escalation via app.notify
    monkeypatch.setattr(webhook, "mark_read", fake_mark)
    # The clinic's own escalation recipient (patient handovers go here, NOT the platform admin).
    monkeypatch.setattr(notify, "clinic_numbers",
                        lambda t, kind: ["clinicstaff"] if kind == "escalation" else [])

    def run(tenant, sender, text, hist):
        c = AgentContext(wa_user=sender, reply="A staff member will follow up.")
        c.needs_human = True
        c.escalation_reason = "complaint"
        return c
    monkeypatch.setattr(webhook, "run_agent", run)
    monkeypatch.setattr(analysis, "generate", lambda s, m, t: LLMResult(text=json.dumps(
        {"customer_name": "Sara", "requested_service": "Dermatology",
         "appointment_preference": "Thursday evening", "insurance": "Bupa",
         "urgency": "high", "sentiment": "neutral", "next_action": "Call back",
         "lead_band": "warm", "lead_score": 50})))

    msg = {"from": user, "id": "wamid." + uuid.uuid4().hex,
           "type": "text", "text": {"body": "I have a complaint"}}
    asyncio.run(webhook._handle_message(msg, None))

    staff = [b for to, b in sent if to == "clinicstaff"]
    assert staff, "clinic staff was not notified"
    assert "AI summary" in staff[0]
    assert "Insurance: Bupa" in staff[0] and "Service: Dermatology" in staff[0]
    # Patient escalations must NOT page the platform admin (technical issues only).
    assert not [b for to, b in sent if to == "999admin"]


def test_webhook_blocks_suspended_tenant_end_to_end(monkeypatch):
    """Plan/status enforcement actually gates WhatsApp: a suspended (non-default) clinic's
    inbound message is blocked — the agent never runs, the patient gets the block notice,
    and no usage is charged."""
    import asyncio
    from app import webhook
    from app.tenancy import current_period
    from app.tools import AgentContext

    sfx = uuid.uuid4().hex[:8]
    pnid = f"PNBLK{sfx}"
    tid = db.create_tenant(f"Blk {sfx}", f"blk-{sfx}", pnid, None, "Asia/Riyadh", None,
                           {"clinic": {"name": "B"}})
    db.set_tenant_status(tid, "suspended")
    user = _user()
    sent, agent_ran = [], {"v": False}

    async def fake_send(to, body, **k):
        sent.append((to, body))

    async def fake_mark(*a, **k):
        return None

    def fake_agent(*a, **k):
        agent_ran["v"] = True
        return AgentContext(wa_user=user, reply="should not run")

    monkeypatch.setattr(webhook, "send_text", fake_send)
    monkeypatch.setattr(webhook, "mark_read", fake_mark)
    monkeypatch.setattr(webhook, "run_agent", fake_agent)
    monkeypatch.setattr(webhook, "USAGE_ENFORCEMENT", True)

    msg = {"from": user, "id": "wamid." + uuid.uuid4().hex, "type": "text", "text": {"body": "hi"}}
    asyncio.run(webhook._handle_message(msg, pnid))

    assert agent_ran["v"] is False                                  # agent never invoked
    assert sent and "currently unavailable" in sent[0][1]           # MSG_UNAVAILABLE sent
    assert db.get_usage(tid, current_period("Asia/Riyadh"))["text_count"] == 0   # not charged


def test_health_endpoint_reports_version():
    from fastapi.testclient import TestClient
    import main
    r = TestClient(main.app).get("/")
    assert "version" in r.json()          # commit SHA marker for deploy verification


def test_list_tenants_includes_connector_type():
    from app.tenancy import current_period
    sfx = uuid.uuid4().hex[:8]
    tid = db.create_tenant(f"Cn {sfx}", f"cn-{sfx}", f"PNCN{sfx}", None, "Asia/Riyadh", None,
                           {"clinic": {"name": "X"},
                            "connector": {"type": "cliniko", "api_key": "k", "business_id": "b"}})
    rows = db.list_tenants(current_period("Asia/Riyadh"))
    row = next(r for r in rows if r["id"] == tid)
    assert row["connector_type"] == "cliniko"        # type is readable (not a secret)


def test_plans_api_includes_connector_type():
    sfx = uuid.uuid4().hex[:8]
    db.create_tenant(f"Cn2 {sfx}", f"cn2-{sfx}", f"PNCN2{sfx}", None, "Asia/Riyadh", None,
                     {"clinic": {"name": "X"},
                      "connector": {"type": "cliniko", "api_key": "k", "business_id": "b"}})
    r = _super_client().get("/api/plans")
    assert r.status_code == 200
    assert any(t["connector_type"] == "cliniko" for t in r.json()["tenants"])


def test_dashboard_flags_failing_whatsapp_sends(monkeypatch):
    import app.wa_client as wa
    c = _super_client()
    monkeypatch.setattr(wa, "_auth_failed_at", None)
    assert c.get("/api/dashboard").json()["wa_send_failing"] is False
    wa._note_send_result(401)                 # a 401 flips the flag
    assert c.get("/api/dashboard").json()["wa_send_failing"] is True
    wa._note_send_result(200)                 # a later success clears it
    assert c.get("/api/dashboard").json()["wa_send_failing"] is False


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


# --- Clinic-wise admin views (overview, usage, issues access control) ---
def _clinic_client(tenant_id: int):
    """A TestClient logged in as a clinic staff user for `tenant_id`."""
    from fastapi.testclient import TestClient
    from app.auth import hash_password
    import main
    uname = "staff-" + uuid.uuid4().hex[:8]
    db.set_tenant_credentials(tenant_id, uname, hash_password("pw-123"))
    c = TestClient(main.app)
    r = c.post("/api/login", json={"username": uname, "password": "pw-123"})
    assert r.status_code == 200, "clinic login failed"
    return c


def test_overview_is_super_admin_only():
    c = _super_client()
    r = c.get("/api/overview")
    assert r.status_code == 200 and "clinics" in r.json()


def test_super_list_pages_have_clinic_filter():
    c = _super_client()
    for path in ("/api/conversations", "/api/appointments", "/api/reviews", "/api/no-shows"):
        body = c.get(path).json()
        assert body.get("is_super") is True and "clinics" in body, path


def test_clinic_login_gets_dashboard_not_overview():
    c = _clinic_client(_tenant())
    assert c.get("/api/dashboard").status_code == 200    # its own single-clinic dashboard
    assert c.get("/api/overview").status_code == 403      # super-only


def test_issues_are_super_admin_only():
    c = _clinic_client(_tenant())
    assert c.get("/api/logs").status_code == 403          # hidden from clinics
    assert _super_client().get("/api/logs").status_code == 200


def test_clinic_usage_is_available():
    c = _clinic_client(_tenant())
    r = c.get("/api/usage")
    assert r.status_code == 200 and "usage" in r.json()


def test_clinic_cannot_see_other_clinic_via_filter():
    # A clinic login is locked to its own tenant; the ?clinic= filter must be ignored.
    mine, other = _tenant(), _tenant()
    u = _user()
    db.create_appointment(other, u, "Other Pt", "+1", "Dr. X", "Consult",
                          datetime(2026, 6, 9, 10, 0, tzinfo=TZ),
                          datetime(2026, 6, 9, 10, 30, tzinfo=TZ))
    c = _clinic_client(mine)
    rows = c.get(f"/api/appointments?clinic={other}").json()["rows"]
    assert not any(a["patient_name"] == "Other Pt" for a in rows)   # cross-clinic leak blocked
