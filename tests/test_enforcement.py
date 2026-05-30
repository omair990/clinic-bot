"""Tests for plan/quota enforcement (db.get_usage is faked — no DB)."""
from datetime import datetime, timedelta, timezone

import app.tenancy as ten


def _tenant(**kw):
    base = dict(id=1, status="active", timezone="Asia/Riyadh", is_trial=False,
                trial_ends_at=None, voice_enabled=True,
                monthly_text_quota=None, monthly_voice_quota=None)
    base.update(kw)
    return base


def _usage(monkeypatch, text=0, voice=0):
    monkeypatch.setattr(ten.db, "get_usage",
                        lambda *a, **k: {"text_count": text, "voice_count": voice})


def test_none_tenant_allows():
    assert ten.check_quota(None, is_voice=False).allowed


def test_unlimited_plan_allows_even_high_usage(monkeypatch):
    _usage(monkeypatch, text=999999)
    assert ten.check_quota(_tenant(), is_voice=False).allowed


def test_text_quota_blocks_at_limit(monkeypatch):
    _usage(monkeypatch, text=50)
    d = ten.check_quota(_tenant(monthly_text_quota=50), is_voice=False)
    assert not d.allowed and d.reason == "text_quota"


def test_text_under_quota_allows(monkeypatch):
    _usage(monkeypatch, text=49)
    assert ten.check_quota(_tenant(monthly_text_quota=50), is_voice=False).allowed


def test_voice_disabled_blocks(monkeypatch):
    _usage(monkeypatch)
    d = ten.check_quota(_tenant(voice_enabled=False), is_voice=True)
    assert not d.allowed and d.reason == "voice_not_allowed"


def test_voice_quota_blocks(monkeypatch):
    _usage(monkeypatch, voice=500)
    d = ten.check_quota(_tenant(monthly_voice_quota=500), is_voice=True)
    assert not d.allowed and d.reason == "voice_quota"


def test_voice_does_not_count_against_text_quota(monkeypatch):
    _usage(monkeypatch, text=999, voice=0)
    assert ten.check_quota(_tenant(monthly_text_quota=50, monthly_voice_quota=10),
                           is_voice=True).allowed


def test_suspended_blocks(monkeypatch):
    _usage(monkeypatch)
    d = ten.check_quota(_tenant(status="suspended"), is_voice=False)
    assert not d.allowed and d.reason == "suspended"


def test_trial_expired_blocks(monkeypatch):
    _usage(monkeypatch)
    past = datetime.now(timezone.utc) - timedelta(days=1)
    d = ten.check_quota(_tenant(is_trial=True, trial_ends_at=past), is_voice=False)
    assert not d.allowed and d.reason == "trial_expired"


def test_trial_active_allows(monkeypatch):
    _usage(monkeypatch)
    future = datetime.now(timezone.utc) + timedelta(days=3)
    assert ten.check_quota(_tenant(is_trial=True, trial_ends_at=future,
                                   monthly_text_quota=50), is_voice=False).allowed
