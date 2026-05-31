"""Deep end-to-end tests for the no-show recovery feature against a real Postgres.

Mirrors the manual verification: drive the actual `no_show.sweep()` and the real tool
handlers through the DB, with only the outbound WhatsApp HTTP boundary stubbed. Requires
a reachable Postgres (run via `scripts/staging.sh test`); skipped automatically otherwise.
"""
import asyncio
import uuid
from datetime import datetime, timedelta

import pytest

from app import db, no_show
from app.config import TZ

pytestmark = pytest.mark.filterwarnings("ignore")

CLINIC = {
    "clinic": {"name": "NS Test Clinic"},
    "doctors": [{"name": "Dr. Test", "specialty": "gp",
                 "available_days": ["Sunday", "Monday", "Tuesday", "Wednesday",
                                    "Thursday", "Saturday"],
                 "available_hours": "9:00 AM - 1:00 PM, 4:00 PM - 11:00 PM"}],
    "services": [{"name": "Consult", "price_sar": 100, "duration_min": 30}],
}


@pytest.fixture(scope="module")
def tenant():
    try:
        db.init_db()
        if not db.ping():
            pytest.skip("no database reachable")
    except Exception:
        pytest.skip("no database reachable")
    sfx = uuid.uuid4().hex[:8]
    return db.create_tenant(f"NS {sfx}", f"ns-{sfx}", f"PNNS{sfx}", None,
                            "Asia/Riyadh", None, CLINIC)


@pytest.fixture
def wa(monkeypatch):
    """Capture outbound WhatsApp sends (the only external boundary) instead of hitting Meta."""
    sent = []

    async def fake_template(to, name, language, params, **creds):
        sent.append({"kind": "template", "to": to, "name": name, "params": params})

    async def fake_text(to, body, **creds):
        sent.append({"kind": "text", "to": to, "body": body})

    monkeypatch.setattr(no_show, "send_template", fake_template)
    monkeypatch.setattr(no_show, "send_text", fake_text)
    return sent


def _user() -> str:
    return "9665" + uuid.uuid4().hex[:7]


def _seed_past_confirmed(tid: int, user: str) -> int:
    """A confirmed appointment whose 30-min slot ended ~1.5h ago (well past grace)."""
    now = datetime.now(TZ)
    with db.get_conn() as conn:
        row = conn.execute(
            "INSERT INTO appointments (tenant_id, wa_user, patient_name, doctor, service, "
            "start_at, end_at, status) VALUES (%s,%s,%s,%s,%s,%s,%s,'confirmed') RETURNING id",
            (tid, user, "NS Patient", "Dr. Test", "Consult",
             now - timedelta(hours=2), now - timedelta(hours=1, minutes=30))).fetchone()
        conn.commit()
    return row["id"]


def test_sweep_detects_notifies_scores_and_logs(tenant, wa, monkeypatch):
    monkeypatch.setattr(no_show, "NO_SHOW_AUTO_SEND", True)
    monkeypatch.setattr(no_show, "NO_SHOW_USE_TEMPLATES", True)
    monkeypatch.setattr(no_show, "_ENV_TEMPLATES",
                        {"no_show": "no_show_recovery", "followup": "ns_fu", "reminder": "ns_rm"})
    monkeypatch.setattr(no_show, "NO_SHOW_TEMPLATE_LANG", "en")
    user = _user()
    appt_id = _seed_past_confirmed(tenant, user)

    asyncio.run(no_show.sweep())

    # Appointment flipped, follow-up opened at 'notified' with a risk snapshot.
    assert db.get_appointment(tenant, appt_id)["status"] == "no_show"
    fu = db.open_no_show_followup(tenant, user)
    assert fu is not None and fu["stage"] == "notified"
    with db.get_conn() as conn:
        r = conn.execute("SELECT risk_score, risk_band, notified_at FROM no_show_followups "
                         "WHERE appointment_id=%s", (appt_id,)).fetchone()
    assert r["risk_score"] is not None
    assert r["risk_band"] in ("low", "medium", "high")
    assert r["notified_at"] is not None

    # One template message went to this patient with the right name + body param.
    mine = [s for s in wa if s["to"] == user]
    assert len(mine) == 1 and mine[0]["kind"] == "template"
    assert mine[0]["name"] == "no_show_recovery"
    assert mine[0]["params"] == ["Consult with Dr. Test"]

    # Mirrored into the conversation log with the no_show intent.
    conv = db.conversation_thread(user, tenant_id=tenant)
    assert any(c["direction"] == "out" and c["intent"] == "no_show" for c in conv)


def test_followup_then_inactive_transitions(tenant, wa, monkeypatch):
    monkeypatch.setattr(no_show, "NO_SHOW_AUTO_SEND", True)
    monkeypatch.setattr(no_show, "NO_SHOW_USE_TEMPLATES", False)
    user = _user()
    appt_id = _seed_past_confirmed(tenant, user)

    asyncio.run(no_show.sweep())                       # -> notified
    assert db.open_no_show_followup(tenant, user)["stage"] == "notified"

    with db.get_conn() as conn:                        # age the notification past the window
        conn.execute("UPDATE no_show_followups SET notified_at = now() - interval '2 days' "
                     "WHERE appointment_id=%s", (appt_id,))
        conn.commit()
    asyncio.run(no_show.sweep())                       # -> followed_up
    assert db.open_no_show_followup(tenant, user)["stage"] == "followed_up"

    with db.get_conn() as conn:
        conn.execute("UPDATE no_show_followups SET followup_at = now() - interval '2 days' "
                     "WHERE appointment_id=%s", (appt_id,))
        conn.commit()
    asyncio.run(no_show.sweep())                       # -> inactive
    assert db.open_no_show_followup(tenant, user) is None   # no longer "open"
    with db.get_conn() as conn:
        stage = conn.execute("SELECT stage FROM no_show_followups WHERE appointment_id=%s",
                             (appt_id,)).fetchone()["stage"]
    assert stage == "inactive"


def test_patient_reply_halts_followup(tenant, wa, monkeypatch):
    monkeypatch.setattr(no_show, "NO_SHOW_AUTO_SEND", True)
    monkeypatch.setattr(no_show, "NO_SHOW_USE_TEMPLATES", False)
    user = _user()
    appt_id = _seed_past_confirmed(tenant, user)

    asyncio.run(no_show.sweep())                       # -> notified
    with db.get_conn() as conn:
        conn.execute("UPDATE no_show_followups SET notified_at = now() - interval '2 days' "
                     "WHERE appointment_id=%s", (appt_id,))
        conn.commit()
    db.log_message(tenant, user, "in", "sorry, I forgot!")   # reply after notified_at

    asyncio.run(no_show.sweep())
    # A reply suppresses the automated nudge — still 'notified', not advanced.
    assert db.open_no_show_followup(tenant, user)["stage"] == "notified"


def test_cancel_via_tool_resolves_followup(tenant, wa, monkeypatch):
    from app.tools import AgentContext, dispatch
    monkeypatch.setattr(no_show, "NO_SHOW_AUTO_SEND", False)
    user = _user()
    appt_id = _seed_past_confirmed(tenant, user)
    asyncio.run(no_show.sweep())                       # detected (no send)

    ctx = AgentContext(wa_user=user, tenant_id=tenant, clinic_data=CLINIC,
                       no_show=db.open_no_show_followup(tenant, user))
    out = dispatch("cancel_appointment", {"appointment_id": appt_id}, ctx)
    assert out.get("cancelled")

    assert db.get_appointment(tenant, appt_id)["status"] == "cancelled"
    with db.get_conn() as conn:
        r = conn.execute("SELECT outcome, stage FROM no_show_followups WHERE appointment_id=%s",
                         (appt_id,)).fetchone()
    assert r["stage"] == "resolved" and r["outcome"] == "cancel"


def test_record_reason_via_tool(tenant, wa, monkeypatch):
    from app.tools import AgentContext, dispatch
    monkeypatch.setattr(no_show, "NO_SHOW_AUTO_SEND", False)
    user = _user()
    appt_id = _seed_past_confirmed(tenant, user)
    asyncio.run(no_show.sweep())

    ctx = AgentContext(wa_user=user, tenant_id=tenant, clinic_data=CLINIC,
                       no_show=db.open_no_show_followup(tenant, user))
    out = dispatch("record_no_show_response",
                   {"appointment_id": appt_id, "outcome": "call",
                    "reason": "I totally forgot about it"}, ctx)
    assert out["recorded"]
    with db.get_conn() as conn:
        r = conn.execute("SELECT reason, outcome, stage FROM no_show_followups "
                         "WHERE appointment_id=%s", (appt_id,)).fetchone()
    assert r["reason"] == "forgot"      # free text mapped onto the canonical reason
    assert r["outcome"] == "call"
    assert r["stage"] == "resolved"


def test_reschedule_revives_a_no_show(tenant, wa, monkeypatch):
    from app.tools import AgentContext, dispatch
    monkeypatch.setattr(no_show, "NO_SHOW_AUTO_SEND", False)
    user = _user()
    appt_id = _seed_past_confirmed(tenant, user)
    asyncio.run(no_show.sweep())
    assert db.get_appointment(tenant, appt_id)["status"] == "no_show"

    ctx = AgentContext(wa_user=user, tenant_id=tenant, clinic_data=CLINIC,
                       no_show=db.open_no_show_followup(tenant, user))
    # Ask the real availability tool for a concrete free slot, then reschedule into it.
    avail = dispatch("check_availability",
                     {"doctor": "Dr. Test", "date": "sunday", "service": "Consult"}, ctx)
    assert avail.get("available_times"), avail
    out = dispatch("reschedule_appointment",
                   {"appointment_id": appt_id, "date": avail["date"],
                    "time": avail["available_times"][0]}, ctx)
    assert out.get("rescheduled"), out

    assert db.get_appointment(tenant, appt_id)["status"] == "confirmed"
    with db.get_conn() as conn:
        r = conn.execute("SELECT outcome, stage FROM no_show_followups WHERE appointment_id=%s",
                         (appt_id,)).fetchone()
    assert r["stage"] == "resolved" and r["outcome"] == "reschedule"


def test_predictor_scores_and_reminds_high_risk(tenant, wa, monkeypatch):
    monkeypatch.setattr(no_show, "NO_SHOW_PREDICTOR", True)
    monkeypatch.setattr(no_show, "NO_SHOW_AUTO_SEND", False)
    monkeypatch.setattr(no_show, "NO_SHOW_USE_TEMPLATES", False)
    monkeypatch.setattr(no_show, "PRE_APPT_CONFIRM_ENABLED", True)
    monkeypatch.setattr(no_show, "PRE_APPT_CONFIRM_LEAD_HOURS", 48)
    user = _user()
    now = datetime.now(TZ)
    with db.get_conn() as conn:
        for _ in range(2):     # two prior no-shows + a cancellation -> deterministically high
            conn.execute("INSERT INTO appointments (tenant_id,wa_user,doctor,service,start_at,"
                         "end_at,status) VALUES (%s,%s,'Dr. Test','Consult',%s,%s,'no_show')",
                         (tenant, user, now - timedelta(days=30),
                          now - timedelta(days=30) + timedelta(minutes=30)))
        conn.execute("INSERT INTO appointments (tenant_id,wa_user,doctor,service,start_at,"
                     "end_at,status) VALUES (%s,%s,'Dr. Test','Consult',%s,%s,'cancelled')",
                     (tenant, user, now - timedelta(days=10),
                      now - timedelta(days=10) + timedelta(minutes=30)))
        row = conn.execute("INSERT INTO appointments (tenant_id,wa_user,doctor,service,start_at,"
                           "end_at,status) VALUES (%s,%s,'Dr. Test','Consult',%s,%s,'confirmed') "
                           "RETURNING id",
                           (tenant, user, now + timedelta(hours=12),
                            now + timedelta(hours=12, minutes=30))).fetchone()
        conn.commit()
    upcoming_id = row["id"]

    asyncio.run(no_show.sweep())

    appt = db.get_appointment(tenant, upcoming_id)
    assert appt["risk_score"] is not None and appt["risk_band"] == "high"
    assert appt["reminded_at"] is not None        # the extra high-risk reminder fired once
    mine = [s for s in wa if s["to"] == user]
    assert any("reminder" in s.get("body", "").lower() for s in mine)


def test_pre_appointment_confirmation_sent_to_every_upcoming(tenant, wa, monkeypatch):
    # A brand-new patient (no history => low risk) still gets a confirmation nudge.
    monkeypatch.setattr(no_show, "NO_SHOW_AUTO_SEND", False)
    monkeypatch.setattr(no_show, "NO_SHOW_USE_TEMPLATES", False)
    monkeypatch.setattr(no_show, "PRE_APPT_CONFIRM_ENABLED", True)
    monkeypatch.setattr(no_show, "PRE_APPT_CONFIRM_LEAD_HOURS", 24)
    user = _user()
    now = datetime.now(TZ)
    appt = db.create_appointment(tenant, user, "New Pt", "+1", "Dr. Test", "Consult",
                                 now + timedelta(hours=6), now + timedelta(hours=6, minutes=30))
    asyncio.run(no_show.sweep())
    assert db.get_appointment(tenant, appt["id"])["reminded_at"] is not None
    body = next(s["body"] for s in wa if s["to"] == user)
    assert "attend" in body.lower() and "1 to confirm" in body

    # Second sweep must NOT re-send (reminded_at already set).
    wa.clear()
    asyncio.run(no_show.sweep())
    assert [s for s in wa if s["to"] == user] == []
