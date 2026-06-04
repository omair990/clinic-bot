"""Unit tests for the operations-report aggregation — DB-free (db functions monkeypatched)."""
from datetime import datetime, timedelta

import pytest

from app import reports
from app.config import TZ


def _appt(aid, status, service=None, start=None, wa="111", tenant_id=1):
    return {"id": aid, "tenant_id": tenant_id, "wa_user": wa, "patient_name": "Pat",
            "phone": None, "doctor": "Dr A", "service": service,
            "start_at": start or datetime(2026, 6, 1, 10, tzinfo=TZ),
            "end_at": None, "status": status, "created_at": None}


def _wire(monkeypatch, *, appts, reviews=None, tenant=None,
          msg=None, conv=None):
    monkeypatch.setattr(reports.db, "appointments_in_range",
                        lambda since, until, scope, limit=5000: appts)
    monkeypatch.setattr(reports.db, "reviews_in_range",
                        lambda since, until, scope, limit=5000: reviews or [])
    monkeypatch.setattr(reports.db, "insight_message_stats",
                        lambda scope, since, until: msg or {"messages": 0, "inbound": 0})
    monkeypatch.setattr(reports.db, "insight_conversion",
                        lambda scope, since, until: conv or {"users_messaged": 0,
                                                             "users_booked": 0, "conversion_pct": 0})
    monkeypatch.setattr(reports.db, "get_tenant", lambda tid: tenant)


def test_summary_counts_and_rates(monkeypatch):
    appts = [_appt(1, "completed"), _appt(2, "completed"), _appt(3, "no_show"),
             _appt(4, "cancelled"), _appt(5, "confirmed", wa="222")]
    _wire(monkeypatch, appts=appts, tenant={"id": 1, "clinic_data": {}})
    since = datetime(2026, 6, 1, tzinfo=TZ)
    rep = reports.build_report(1, since, since + timedelta(days=7))
    s = rep["summary"]
    assert s["appointments"] == 5
    assert s["completed"] == 2 and s["no_shows"] == 1 and s["cancelled"] == 1
    assert s["completion_rate"] == 40  # 2/5
    assert s["no_show_rate"] == 20     # 1/5
    assert s["unique_patients"] == 2   # "111" and "222"
    assert rep["status_breakdown"] == {"confirmed": 1, "completed": 2,
                                       "cancelled": 1, "no_show": 1}


def test_estimated_revenue_only_counts_completed_with_price(monkeypatch):
    appts = [_appt(1, "completed", service="Cleaning"),
             _appt(2, "completed", service="Whitening"),   # no price configured → 0
             _appt(3, "no_show", service="Cleaning"),      # not completed → ignored
             _appt(4, "completed", service=None)]          # no service → 0
    tenant = {"id": 1, "clinic_data": {"services": [
        {"name": "Cleaning", "price_sar": 150}, {"name": "Filling", "price_sar": 200}]}}
    _wire(monkeypatch, appts=appts, tenant=tenant)
    since = datetime(2026, 6, 1, tzinfo=TZ)
    rep = reports.build_report(1, since, since + timedelta(days=7))
    assert rep["summary"]["est_revenue"] == 150.0
    assert rep["summary"]["currency"] == "SAR"
    # the per-row price is surfaced for the export
    assert rep["appointments"][0]["price"] == 150.0


def test_revenue_matches_service_case_insensitively(monkeypatch):
    appts = [_appt(1, "completed", service="cleaning ")]  # trailing space + lowercase
    tenant = {"id": 1, "clinic_data": {"services": [{"name": "Cleaning", "price_sar": 150}]}}
    _wire(monkeypatch, appts=appts, tenant=tenant)
    since = datetime(2026, 6, 1, tzinfo=TZ)
    rep = reports.build_report(1, since, since + timedelta(days=7))
    assert rep["summary"]["est_revenue"] == 150.0


def test_review_stats_are_range_accurate(monkeypatch):
    reviews = [
        {"id": 1, "tenant_id": 1, "wa_user": "1", "rating": 5, "comment": "great",
         "stage": "done", "responded_at": None, "created_at": None, "doctor": "A", "service": "X",
         "patient_name": "P"},
        {"id": 2, "tenant_id": 1, "wa_user": "2", "rating": 3, "comment": None,
         "stage": "done", "responded_at": None, "created_at": None, "doctor": "A", "service": "X",
         "patient_name": "P"},
        {"id": 3, "tenant_id": 1, "wa_user": "3", "rating": None, "comment": None,
         "stage": "sent", "responded_at": None, "created_at": None, "doctor": "A", "service": "X",
         "patient_name": "P"},
    ]
    _wire(monkeypatch, appts=[], reviews=reviews, tenant={"id": 1, "clinic_data": {}})
    since = datetime(2026, 6, 1, tzinfo=TZ)
    rep = reports.build_report(1, since, since + timedelta(days=7))
    st = rep["reviews"]["stats"]
    assert st["requested"] == 3 and st["responded"] == 2 and st["rated"] == 2
    assert st["avg_rating"] == 4.0  # (5+3)/2
    assert len(rep["reviews"]["rows"]) == 3


def test_empty_range_has_safe_zero_rates(monkeypatch):
    _wire(monkeypatch, appts=[], tenant={"id": 1, "clinic_data": {}})
    since = datetime(2026, 6, 1, tzinfo=TZ)
    rep = reports.build_report(1, since, since + timedelta(days=7))
    assert rep["summary"]["completion_rate"] == 0
    assert rep["summary"]["no_show_rate"] == 0
    assert rep["summary"]["est_revenue"] == 0


def test_super_scope_builds_price_map_from_all_clinics(monkeypatch):
    appts = [_appt(1, "completed", service="Cleaning", tenant_id=1),
             _appt(2, "completed", service="Consult", tenant_id=2)]
    monkeypatch.setattr(reports.db, "all_active_tenants", lambda: [
        {"id": 1, "clinic_data": {"services": [{"name": "Cleaning", "price_sar": 100}]}},
        {"id": 2, "clinic_data": {"services": [{"name": "Consult", "price_sar": 50}]}}])
    _wire(monkeypatch, appts=appts, tenant=None)
    since = datetime(2026, 6, 1, tzinfo=TZ)
    rep = reports.build_report(None, since, since + timedelta(days=7))  # all clinics
    assert rep["summary"]["est_revenue"] == 150.0  # 100 + 50 across two clinics


# --- date range parsing ---------------------------------------------------------

def test_parse_range_inclusive_to_day():
    since, until = reports.parse_range("2026-06-01", "2026-06-07")
    assert since == datetime(2026, 6, 1, tzinfo=TZ)
    assert until == datetime(2026, 6, 8, tzinfo=TZ)  # exclusive end = day after "to"


def test_parse_range_defaults_to_last_30_days():
    now = datetime(2026, 6, 10, 15, 0, tzinfo=TZ)
    since, until = reports.parse_range("", "", now)
    assert until == datetime(2026, 6, 11, tzinfo=TZ)
    assert (until - since).days == 31


def test_parse_range_swapped_dates_yield_one_day():
    since, until = reports.parse_range("2026-06-07", "2026-06-01")
    assert until == since + timedelta(days=1)


def test_parse_range_clamps_to_max_span():
    since, until = reports.parse_range("2000-01-01", "2026-06-07")
    assert (until - since).days == reports.MAX_RANGE_DAYS


@pytest.mark.parametrize("bad", ["", "not-a-date", "2026-13-99"])
def test_parse_day_tolerates_garbage(bad):
    assert reports._parse_day(bad) is None
