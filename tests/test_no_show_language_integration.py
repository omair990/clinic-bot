"""Integration: proactive no-show copy localised to the patient's language, against a real DB.

Hits real Postgres — creates tenants, logs conversations, runs the actual `recent_history`
SQL round-trip through `_patient_lang`, and drives `send_no_show_notification` end-to-end with
only the WhatsApp HTTP call mocked. Skips when no DB is reachable."""
import asyncio
import uuid

import pytest

from app import db, no_show


def _db_ok():
    try:
        db.init_db()
        with db.get_conn() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_ok(), reason="no database reachable")


def _tenant(default_language=None):
    sfx = uuid.uuid4().hex[:8]
    clinic = {"name": "N"}
    if default_language:
        clinic["default_language"] = default_language
    return db.create_tenant(f"N {sfx}", f"n-{sfx}", f"PNN{sfx}", None, "Asia/Riyadh", None,
                            {"clinic": clinic})


def _wa():
    return f"966{uuid.uuid4().hex[:7]}"


def test_patient_lang_from_recent_arabic_message():
    tid, wa = _tenant(), _wa()
    db.log_message(tid, wa, "in", "من اي دولة")
    assert no_show._patient_lang(tid, wa, {}) == "ar"


def test_patient_lang_uses_latest_inbound_not_earlier():
    tid, wa = _tenant(), _wa()
    db.log_message(tid, wa, "in", "hello can you help me please")   # earlier English
    db.log_message(tid, wa, "out", "اهلا وسهلا")                    # our reply (outbound, ignored)
    db.log_message(tid, wa, "in", "هل اقدر اقدم عن شكوى عن طريقك")  # latest inbound is Arabic
    assert no_show._patient_lang(tid, wa, {}) == "ar"


def test_patient_lang_falls_back_to_clinic_default():
    tid, wa = _tenant(default_language="Arabic"), _wa()
    db.log_message(tid, wa, "in", "123")                            # undetectable
    tenant = {"clinic_data": {"clinic": {"default_language": "Arabic"}}}
    assert no_show._patient_lang(tid, wa, tenant) == "ar"


def test_patient_lang_none_with_no_history():
    tid, wa = _tenant(), _wa()
    assert no_show._patient_lang(tid, wa, {}) is None


def test_send_no_show_notification_logs_arabic_body(monkeypatch):
    tid, wa = _tenant(), _wa()
    db.log_message(tid, wa, "in", "من اي دولة")                    # Arabic-speaking patient

    sent = {}

    async def fake_send_text(to, body, **creds):
        sent["body"] = body

    monkeypatch.setattr(no_show, "send_text", fake_send_text)

    asyncio.run(no_show.send_no_show_notification(
        to=wa, service="Cavity Filling", doctor="Dr. Hassan Al-Qahtani",
        creds={"phone_number_id": "x", "access_token": "y"},
        tenant_id=tid, followup_id=1, tenant={}, advance=False))

    assert "إعادة جدولة الموعد" in sent["body"]                     # Arabic "Reschedule"
    assert "Reschedule" not in sent["body"]
    # The logged conversation row (dashboard + agent history) mirrors the Arabic body.
    last_out = [m for m in db.recent_history(tid, wa) if m["direction"] == "out"][-1]
    assert "إلغاء العلاج" in last_out["message"]


def test_send_no_show_notification_english_patient(monkeypatch):
    tid, wa = _tenant(), _wa()
    db.log_message(tid, wa, "in", "yes please reschedule me for next week")

    sent = {}

    async def fake_send_text(to, body, **creds):
        sent["body"] = body

    monkeypatch.setattr(no_show, "send_text", fake_send_text)

    asyncio.run(no_show.send_no_show_notification(
        to=wa, service="Cleaning", doctor="Dr. Hana",
        creds={"phone_number_id": "x", "access_token": "y"},
        tenant_id=tid, followup_id=1, tenant={}, advance=False))

    assert "Reschedule" in sent["body"]
