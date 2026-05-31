"""check_availability surfaces the booking lead-time so the bot can say 'too soon'
instead of 'not open'. DB access (booked_intervals) is stubbed; clock is pinned."""
from datetime import datetime

from app import tools
from app.config import BOOKING_LEAD_HOURS, TZ
from app.tools import AgentContext

CLINIC = {
    "clinic": {"name": "Hint Test"},
    "doctors": [{"name": "Dr. T", "specialty": "gp",
                 "available_days": ["Monday", "Tuesday", "Wednesday", "Thursday",
                                    "Friday", "Saturday", "Sunday"],
                 "available_hours": "9:00 AM - 1:00 PM, 5:00 PM - 9:00 PM"}],
    "services": [{"name": "Consult", "price_sar": 100, "duration_min": 20}],
}


def _ctx():
    return AgentContext(wa_user="x", tenant_id=0, clinic_data=CLINIC)


def test_lead_time_hint_present_for_today(monkeypatch):
    fixed = datetime(2026, 6, 1, 9, 0, tzinfo=TZ)   # Monday 09:00, doctor works
    monkeypatch.setattr(tools, "_now", lambda: fixed)
    monkeypatch.setattr(tools.db, "booked_intervals", lambda *a, **k: [])

    res = tools.dispatch("check_availability",
                         {"doctor": "Dr. T", "date": "today", "service": "Consult"}, _ctx())

    assert res["booking_lead_hours"] == BOOKING_LEAD_HOURS
    # 09:00 + 2h lead => earliest bookable today is 11:00
    assert res["earliest_bookable_today"] == "11:00"
    assert "too soon" in res["lead_time_note"]
    # A 09:00 slot exists in working hours but is suppressed by the lead-time floor.
    assert "09:00" not in res["available_times"]
    assert "11:00" in res["available_times"]


def test_no_lead_time_hint_for_future_date(monkeypatch):
    fixed = datetime(2026, 6, 1, 9, 0, tzinfo=TZ)
    monkeypatch.setattr(tools, "_now", lambda: fixed)
    monkeypatch.setattr(tools.db, "booked_intervals", lambda *a, **k: [])

    res = tools.dispatch("check_availability",
                         {"doctor": "Dr. T", "date": "2026-06-08", "service": "Consult"}, _ctx())

    assert res["booking_lead_hours"] == BOOKING_LEAD_HOURS   # policy always reported
    assert "earliest_bookable_today" not in res              # lead-time floor only matters today
    assert "lead_time_note" not in res
    assert "09:00" in res["available_times"]                 # full day open for a future date
