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
