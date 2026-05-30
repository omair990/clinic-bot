"""Tests for tenant usage metering (no DB — db calls are faked)."""
import app.tenancy as ten


def test_current_period_format():
    p = ten.current_period("Asia/Riyadh")
    assert len(p) == 7 and p[4] == "-"      # YYYY-MM


def test_current_period_bad_tz_falls_back():
    assert len(ten.current_period("Not/AZone")) == 7


def test_record_usage_counts_text_vs_voice(monkeypatch):
    calls = []
    monkeypatch.setattr(ten.db, "incr_usage",
                        lambda tid, period, *, text=0, voice=0: calls.append((tid, text, voice)))
    ten.record_usage({"id": 5, "timezone": "Asia/Riyadh"}, is_voice=False)
    ten.record_usage({"id": 5, "timezone": "Asia/Riyadh"}, is_voice=True)
    assert calls == [(5, 1, 0), (5, 0, 1)]


def test_record_usage_none_tenant_is_noop():
    ten.record_usage(None, is_voice=False)   # must not raise


def test_record_usage_swallows_db_errors(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(ten.db, "incr_usage", boom)
    ten.record_usage({"id": 1, "timezone": "Asia/Riyadh"}, is_voice=False)  # must not raise
