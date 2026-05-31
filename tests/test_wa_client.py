"""Tests for per-tenant WhatsApp credential resolution."""
import app.wa_client as wa


def test_overrides_take_precedence():
    assert wa._resolve_creds("PN123", "TOK456") == ("PN123", "TOK456")


def test_falls_back_to_platform_env(monkeypatch):
    monkeypatch.setattr(wa, "WA_PHONE_NUMBER_ID", "ENVPN")
    monkeypatch.setattr(wa, "WA_ACCESS_TOKEN", "ENVTOK")
    assert wa._resolve_creds(None, None) == ("ENVPN", "ENVTOK")
    assert wa._resolve_creds("", "") == ("ENVPN", "ENVTOK")   # empty == use default


def test_messages_url_uses_given_number():
    assert wa._messages_url("PN999").endswith("/PN999/messages")


def test_template_payload_with_params():
    p = wa.build_template_payload("966500", "no_show_recovery", "en", ["Dental Checkup with Dr. K"])
    assert p["type"] == "template"
    assert p["to"] == "966500"
    assert p["template"]["name"] == "no_show_recovery"
    assert p["template"]["language"]["code"] == "en"
    body = p["template"]["components"][0]
    assert body["type"] == "body"
    assert body["parameters"] == [{"type": "text", "text": "Dental Checkup with Dr. K"}]


def test_template_payload_without_params_omits_components():
    p = wa.build_template_payload("966500", "reminder", "ar")
    assert "components" not in p["template"]
    assert p["template"]["language"]["code"] == "ar"
