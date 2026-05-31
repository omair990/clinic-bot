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
