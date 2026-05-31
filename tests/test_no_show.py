"""Unit tests for the no-show risk score — pure, no DB or network."""
from app.no_show import REASON_LABELS, REASONS, compute_risk


def test_new_patient_baseline_is_low():
    # baseline 15 + new-patient 10 = 25
    score, band = compute_risk({})
    assert score == 25
    assert band == "low"


def test_loyal_patient_is_low():
    # 15 - min(6*6, 30) = 15 - 30 -> clamped to 0
    score, band = compute_risk({"completed": 6})
    assert score == 0
    assert band == "low"


def test_repeat_no_shower_is_high():
    score, band = compute_risk({"no_shows": 2, "cancellations": 1, "hour": 20})
    assert score > 65
    assert band == "high"


def test_band_thresholds():
    assert compute_risk({})[1] == "low"                       # 25
    assert compute_risk({"cancellations": 2})[1] == "medium"  # 15 + 16 = 31
    assert compute_risk({"no_shows": 2, "cancellations": 1, "hour": 20})[1] == "high"


def test_score_is_clamped_0_100():
    high, _ = compute_risk({"no_shows": 10, "cancellations": 10, "hour": 20, "lead_hours": 1})
    assert high == 100
    low, _ = compute_risk({"completed": 99})
    assert low == 0


def test_last_minute_booking_raises_risk():
    base = compute_risk({"hour": 12})[0]
    rushed = compute_risk({"hour": 12, "lead_hours": 1})[0]
    assert rushed == base + 10


def test_reason_labels_cover_enum():
    for r in REASONS:
        assert r in REASON_LABELS


def test_resolve_template_off_by_default(monkeypatch):
    import app.no_show as ns
    monkeypatch.setattr(ns, "NO_SHOW_USE_TEMPLATES", False)
    assert ns.resolve_template("no_show", {"clinic_data": {}}) is None


def test_resolve_template_uses_env_default(monkeypatch):
    import app.no_show as ns
    monkeypatch.setattr(ns, "NO_SHOW_USE_TEMPLATES", True)
    monkeypatch.setattr(ns, "_ENV_TEMPLATES", {"no_show": "env_no_show"})
    monkeypatch.setattr(ns, "NO_SHOW_TEMPLATE_LANG", "en")
    t = ns.resolve_template("no_show", None)
    assert t == {"name": "env_no_show", "language": "en"}


def test_resolve_template_tenant_override_wins(monkeypatch):
    import app.no_show as ns
    monkeypatch.setattr(ns, "NO_SHOW_USE_TEMPLATES", True)
    monkeypatch.setattr(ns, "_ENV_TEMPLATES", {"no_show": "env_no_show"})
    tenant = {"clinic_data": {"no_show_templates": {"no_show": "clinic_tmpl", "language": "ar"}}}
    t = ns.resolve_template("no_show", tenant)
    assert t == {"name": "clinic_tmpl", "language": "ar"}


def test_resolve_template_none_when_no_name(monkeypatch):
    import app.no_show as ns
    monkeypatch.setattr(ns, "NO_SHOW_USE_TEMPLATES", True)
    monkeypatch.setattr(ns, "_ENV_TEMPLATES", {"no_show": ""})
    assert ns.resolve_template("no_show", {"clinic_data": {}}) is None


# --- Send-path routing (regression for the WhatsApp template path) ---
# No DB/network: the WhatsApp client and the two DB writes in _send_and_log are stubbed,
# so this asserts purely how send_no_show_notification *routes* the outbound message.

def _run_notification(monkeypatch, *, templates_on, tenant):
    import asyncio
    import app.no_show as ns
    sent = []

    async def fake_template(to, name, language, params, **creds):
        sent.append({"kind": "template", "to": to, "name": name,
                     "language": language, "params": params})

    async def fake_text(to, body, **creds):
        sent.append({"kind": "text", "to": to, "body": body})

    monkeypatch.setattr(ns, "send_template", fake_template)
    monkeypatch.setattr(ns, "send_text", fake_text)
    monkeypatch.setattr(ns, "NO_SHOW_USE_TEMPLATES", templates_on)
    monkeypatch.setattr(ns, "_ENV_TEMPLATES", {"no_show": "no_show_recovery"})
    monkeypatch.setattr(ns, "NO_SHOW_TEMPLATE_LANG", "en")
    monkeypatch.setattr(ns.db, "log_message", lambda *a, **k: None)
    monkeypatch.setattr(ns.db, "set_followup_stage", lambda *a, **k: None)

    asyncio.run(ns.send_no_show_notification(
        to="966500000001", service="Dental Checkup", doctor="Dr. Khalid",
        creds={"phone_number_id": None, "access_token": None},
        tenant_id=1, followup_id=1, tenant=tenant))
    return sent


def test_notification_uses_template_when_enabled(monkeypatch):
    sent = _run_notification(monkeypatch, templates_on=True, tenant={"clinic_data": {}})
    assert len(sent) == 1
    msg = sent[0]
    assert msg["kind"] == "template"
    assert msg["name"] == "no_show_recovery"
    assert msg["language"] == "en"
    assert msg["params"] == ["Dental Checkup with Dr. Khalid"]


def test_notification_uses_free_text_when_disabled(monkeypatch):
    sent = _run_notification(monkeypatch, templates_on=False, tenant=None)
    assert len(sent) == 1
    assert sent[0]["kind"] == "text"
    assert "missed" in sent[0]["body"].lower()
