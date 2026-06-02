"""Notification routing (app.notify): clinic recipients vs platform technical alerts.
Pure logic — WhatsApp + settings are stubbed, no DB."""
import asyncio

from app import notify


def _tenant(recips=None, owner=None):
    cd = {}
    if recips is not None:
        cd["notifications"] = {"recipients": recips}
    if owner is not None:
        cd["owner_wa_number"] = owner
    return {"wa_phone_number_id": "PN1", "wa_access_token": "tok", "clinic_data": cd}


def test_recipients_defaults_escalation_on_digest_off():
    t = _tenant([{"label": "Owner", "number": "9665"}])
    r = notify.recipients(t)[0]
    assert r["escalation"] is True and r["digest"] is False and r["label"] == "Owner"


def test_clinic_numbers_filter_by_kind_and_dedupe():
    t = _tenant([
        {"label": "Desk", "number": "9665", "escalation": True, "digest": False},
        {"label": "Owner", "number": "9666", "escalation": True, "digest": True},
        {"label": "Dup", "number": "9665", "escalation": True, "digest": False},  # duplicate number
        {"label": "Blank", "number": "  ", "escalation": True},                    # ignored
    ])
    assert notify.clinic_numbers(t, "escalation") == ["9665", "9666"]
    assert notify.clinic_numbers(t, "digest") == ["9666"]


def test_legacy_owner_number_gets_both_kinds():
    t = _tenant(owner="9665")
    assert notify.clinic_numbers(t, "escalation") == ["9665"]
    assert notify.clinic_numbers(t, "digest") == ["9665"]


def test_no_recipients_returns_empty():
    assert notify.clinic_numbers(_tenant(), "escalation") == []
    assert notify.clinic_numbers(None, "digest") == []


def test_tech_numbers_split_and_dedupe(monkeypatch):
    from app import settings
    monkeypatch.setattr(settings, "get",
                        lambda key, default=None: "999a, 999b;999a , 999c" if key == "ADMIN_WA_NUMBER" else default)
    assert notify.tech_numbers() == ["999a", "999b", "999c"]


def test_notify_clinic_sends_to_escalation_recipients(monkeypatch):
    from app import wa_client
    sent = []

    async def fake(to, body, **k):
        sent.append((to, body, k.get("phone_number_id")))
    monkeypatch.setattr(wa_client, "send_text", fake)
    t = _tenant([{"label": "Owner", "number": "9665", "escalation": True},
                 {"label": "Acct", "number": "9666", "escalation": False, "digest": True}])
    n = asyncio.run(notify.notify_clinic(t, "hi", kind="escalation"))
    assert n == 1 and sent == [("9665", "hi", "PN1")]   # sent from the clinic's WA number


def test_notify_tech_sends_to_admin_numbers(monkeypatch):
    from app import settings, wa_client
    monkeypatch.setattr(settings, "get",
                        lambda key, default=None: "999a,999b" if key == "ADMIN_WA_NUMBER" else default)
    sent = []

    async def fake(to, body, **k):
        sent.append(to)
    monkeypatch.setattr(wa_client, "send_text", fake)
    n = asyncio.run(notify.notify_tech("down"))
    assert n == 2 and sent == ["999a", "999b"]
