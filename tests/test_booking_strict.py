"""Layer 1: the booking tool must re-read the DB and refuse to report a booking that
didn't persist. Requires Postgres (for db.get_appointment); auto-skips otherwise."""
from datetime import date, datetime, time, timedelta

import pytest

from app import db
from app.config import TZ
from app.tools import AgentContext, dispatch


@pytest.fixture(scope="module", autouse=True)
def _db():
    try:
        db.init_db()
        if not db.ping():
            pytest.skip("no database reachable")
    except Exception:
        pytest.skip("no database reachable")


CLINIC = {
    "doctors": [{"name": "Dr. T", "specialty": "gp",
                 "available_days": ["Sunday", "Monday", "Tuesday", "Wednesday",
                                    "Thursday", "Saturday", "Friday"],
                 "available_hours": "9:00 AM - 11:00 PM"}],
    "services": [{"name": "Consult", "price_sar": 100, "duration_min": 30}],
}


class _PhantomConnector:
    """Returns an appointment id that was never written to our DB (simulates an external
    connector that acked but didn't actually land, or a silent write failure)."""
    def __init__(self):
        self.slot = datetime.combine(date.today() + timedelta(days=1),
                                     time(17, 0), tzinfo=TZ)

    def available_slots(self, doctor, on, duration_min, now):
        return [self.slot]

    def create_appointment(self, **kw):
        return {"id": 999_999_999}   # not in the database


def test_phantom_booking_is_rejected_not_reported_as_booked():
    ctx = AgentContext(wa_user="966500000999", tenant_id=1, clinic_data=CLINIC,
                       connector=_PhantomConnector())
    nxt = date.today() + timedelta(days=1)
    out = dispatch("book_appointment", {
        "patient_name": "Test", "doctor": "Dr. T", "service": "Consult",
        "date": nxt.isoformat(), "time": "17:00"}, ctx)

    assert out.get("error") == "booking_failed", out      # not booked
    assert "booked" not in out
    assert ctx.booked_ids == []                            # nothing recorded as booked
