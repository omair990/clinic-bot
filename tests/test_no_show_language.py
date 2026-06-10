"""Proactive no-show copy must be localised to the patient's language (not always English).

Exercises the real glue — `_patient_lang`'s history scan + clinic-default fallback and the
`send_no_show_notification` send path — with only the DB I/O stubbed, so the actual language
detection and control flow run. No DB or network needed."""
import asyncio

import pytest

from app import no_show


def _stub_history(monkeypatch, rows):
    monkeypatch.setattr(no_show.db, "recent_history", lambda tid, wa, limit=10: rows)


def test_patient_lang_from_recent_arabic_message(monkeypatch):
    _stub_history(monkeypatch, [{"direction": "in", "message": "من اي دولة"}])
    assert no_show._patient_lang(1, "966x", {}) == "ar"


def test_patient_lang_uses_latest_inbound_ignoring_outbound(monkeypatch):
    # Earlier English, our Arabic reply (outbound, must be ignored), latest inbound Arabic.
    _stub_history(monkeypatch, [
        {"direction": "in", "message": "hello can you help me please"},
        {"direction": "out", "message": "اهلا وسهلا"},
        {"direction": "in", "message": "هل اقدر اقدم عن شكوى عن طريقك"},
    ])
    assert no_show._patient_lang(1, "966x", {}) == "ar"


def test_patient_lang_ignores_outbound_only_history(monkeypatch):
    # Only our own (outbound) messages exist → no signal from the patient.
    _stub_history(monkeypatch, [{"direction": "out", "message": "مرحبا بك"}])
    tenant = {"clinic_data": {"clinic": {"default_language": "Arabic"}}}
    assert no_show._patient_lang(1, "966x", tenant) == "ar"


def test_patient_lang_falls_back_to_clinic_default(monkeypatch):
    _stub_history(monkeypatch, [{"direction": "in", "message": "123"}])  # digits → undetectable
    tenant = {"clinic_data": {"clinic": {"default_language": "Arabic"}}}
    assert no_show._patient_lang(1, "966x", tenant) == "ar"


def test_patient_lang_none_when_no_signal_and_no_default(monkeypatch):
    _stub_history(monkeypatch, [])
    assert no_show._patient_lang(1, "966x", {}) is None        # → English copy downstream


def test_patient_lang_survives_db_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(no_show.db, "recent_history", boom)
    tenant = {"clinic_data": {"clinic": {"default_language": "Arabic"}}}
    assert no_show._patient_lang(1, "966x", tenant) == "ar"    # degrades to default, no crash


def test_send_no_show_notification_sends_arabic_body(monkeypatch):
    _stub_history(monkeypatch, [{"direction": "in", "message": "من اي دولة"}])
    monkeypatch.setattr(no_show.db, "log_message", lambda *a, **k: 1)
    monkeypatch.setattr(no_show, "publish", lambda *a, **k: None)

    sent = {}

    async def fake_send_text(to, body, **creds):
        sent["body"] = body

    monkeypatch.setattr(no_show, "send_text", fake_send_text)

    asyncio.run(no_show.send_no_show_notification(
        to="966x", service="Cavity Filling", doctor="Dr. Hassan Al-Qahtani",
        creds={"phone_number_id": "p", "access_token": "t"},
        tenant_id=1, followup_id=1, tenant={}, advance=False))

    assert "إعادة جدولة الموعد" in sent["body"]                 # Arabic "Reschedule"
    assert "Reschedule" not in sent["body"]


def test_send_no_show_notification_stays_english_for_english_patient(monkeypatch):
    _stub_history(monkeypatch, [{"direction": "in", "message": "yes please reschedule me"}])
    monkeypatch.setattr(no_show.db, "log_message", lambda *a, **k: 1)
    monkeypatch.setattr(no_show, "publish", lambda *a, **k: None)

    sent = {}

    async def fake_send_text(to, body, **creds):
        sent["body"] = body

    monkeypatch.setattr(no_show, "send_text", fake_send_text)

    asyncio.run(no_show.send_no_show_notification(
        to="966x", service="Cleaning", doctor="Dr. Hana",
        creds={"phone_number_id": "p", "access_token": "t"},
        tenant_id=1, followup_id=1, tenant={}, advance=False))

    assert "Reschedule" in sent["body"]
