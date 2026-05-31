"""GoogleCalendarConnector logic, exercised with a fake CalendarClient (no real Google).
Mirror writes hit a real Postgres; auto-skips without one."""
import uuid
from datetime import date, datetime, timedelta

import pytest

from app import connectors, db
from app.config import TZ


@pytest.fixture(scope="module", autouse=True)
def _db():
    try:
        db.init_db()
        if not db.ping():
            pytest.skip("no database reachable")
    except Exception:
        pytest.skip("no database reachable")


class FakeCalendar(connectors.CalendarClient):
    def __init__(self, busy=None):
        self.busy = busy or []          # list[(start,end)]
        self.created = []               # (cal, summary, start, end)
        self.patched = []
        self.deleted = []
        self._seq = 0

    def free_busy(self, calendar_id, time_min, time_max):
        return [b for b in self.busy if b[0] >= time_min and b[1] <= time_max]

    def create_event(self, calendar_id, summary, start, end, description=""):
        self._seq += 1
        self.created.append((calendar_id, summary, start, end))
        return f"evt_{self._seq}"

    def patch_event(self, calendar_id, event_id, start, end):
        self.patched.append((calendar_id, event_id, start, end))

    def delete_event(self, calendar_id, event_id):
        self.deleted.append((calendar_id, event_id))


DOCTOR = {"name": "Dr. Cal", "specialty": "gp",
          "available_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                             "Saturday", "Sunday"],
          "available_hours": "9:00 AM - 5:00 PM"}


def _conf(busy=None):
    return {"type": "google_calendar", "calendars": {"Dr. Cal": "cal_dr_cal"}}


def _tenant():
    sfx = uuid.uuid4().hex[:8]
    return db.create_tenant(f"G {sfx}", f"g-{sfx}", f"PNG{sfx}", None, "Asia/Riyadh", None,
                            {"clinic": {"name": "G"}})


def test_capabilities_full():
    c = connectors.GoogleCalendarConnector(1, _conf(), FakeCalendar())
    assert connectors.READ_AVAILABILITY in c.capabilities() and connectors.CREATE in c.capabilities()


def test_available_slots_excludes_google_busy():
    # Busy 10:00-11:00 on a working day => those slots disappear; 9:00 stays.
    on = date(2026, 6, 8)   # Monday
    busy = [(datetime(2026, 6, 8, 10, 0, tzinfo=TZ), datetime(2026, 6, 8, 11, 0, tzinfo=TZ))]
    c = connectors.GoogleCalendarConnector(1, _conf(), FakeCalendar(busy))
    now = datetime(2026, 6, 7, 9, 0, tzinfo=TZ)   # day before => no lead-time cutoff
    slots = c.available_slots(DOCTOR, on, 30, now)
    times = {s.strftime("%H:%M") for s in slots}
    assert "09:00" in times
    assert "10:00" not in times and "10:30" not in times   # blocked by Google busy


def test_no_calendar_for_doctor_yields_no_slots():
    c = connectors.GoogleCalendarConnector(1, {"calendars": {}}, FakeCalendar())
    assert c.available_slots(DOCTOR, date(2026, 6, 8), 30,
                             datetime(2026, 6, 7, 9, 0, tzinfo=TZ)) == []


def test_create_mirrors_locally_and_writes_event():
    tid = _tenant()
    user = "9665" + uuid.uuid4().hex[:7]
    fake = FakeCalendar()
    c = connectors.GoogleCalendarConnector(tid, _conf(), fake)
    now = datetime.now(TZ)
    start, end = now + timedelta(days=2), now + timedelta(days=2, minutes=30)
    row = c.create_appointment(wa_user=user, patient_name="Sara", phone="+1", doctor="Dr. Cal",
                               service="Consult", start=start, end=end)
    assert row["id"] and row.get("external_id") == "evt_1"      # event created + linked
    assert fake.created and fake.created[0][0] == "cal_dr_cal"  # on the doctor's calendar
    assert db.get_appointment(tid, row["id"])["external_id"] == "evt_1"   # mirrored


def test_reschedule_patches_event_and_mirror():
    tid = _tenant()
    user = "9665" + uuid.uuid4().hex[:7]
    fake = FakeCalendar()
    c = connectors.GoogleCalendarConnector(tid, _conf(), fake)
    now = datetime.now(TZ)
    row = c.create_appointment(wa_user=user, patient_name="Sara", phone="+1", doctor="Dr. Cal",
                               service="Consult", start=now + timedelta(days=2),
                               end=now + timedelta(days=2, minutes=30))
    new_start = now + timedelta(days=3)
    moved = c.reschedule(row["id"], new_start, new_start + timedelta(minutes=30))
    assert not moved.get("conflict")
    assert fake.patched and fake.patched[0][1] == "evt_1"      # patched the right event
    assert db.get_appointment(tid, row["id"])["start_at"].date() == new_start.date()


def test_cancel_deletes_event_and_sets_status():
    tid = _tenant()
    user = "9665" + uuid.uuid4().hex[:7]
    fake = FakeCalendar()
    c = connectors.GoogleCalendarConnector(tid, _conf(), fake)
    now = datetime.now(TZ)
    row = c.create_appointment(wa_user=user, patient_name="Sara", phone="+1", doctor="Dr. Cal",
                               service="Consult", start=now + timedelta(days=2),
                               end=now + timedelta(days=2, minutes=30))
    c.set_status(row["id"], "cancelled")
    assert fake.deleted and fake.deleted[0][1] == "evt_1"
    assert db.get_appointment(tid, row["id"])["status"] == "cancelled"


def test_create_keeps_booking_when_calendar_errors(monkeypatch):
    tid = _tenant()
    user = "9665" + uuid.uuid4().hex[:7]
    fake = FakeCalendar()
    monkeypatch.setattr(fake, "create_event",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("google down")))
    c = connectors.GoogleCalendarConnector(tid, _conf(), fake)
    now = datetime.now(TZ)
    row = c.create_appointment(wa_user=user, patient_name="Sara", phone="+1", doctor="Dr. Cal",
                               service="Consult", start=now + timedelta(days=2),
                               end=now + timedelta(days=2, minutes=30))
    # Booking still exists locally even though the calendar write failed.
    assert row["id"] and row.get("external_id") is None
    assert db.get_appointment(tid, row["id"]) is not None


def test_get_connector_dispatches_to_google(monkeypatch):
    fake = FakeCalendar()
    monkeypatch.setattr(connectors, "_build_google_client", lambda conf: fake)
    tenant = {"id": 7, "clinic_data": {"connector": {"type": "google_calendar",
                                                     "refresh_token": "x", "calendars": {}}}}
    c = connectors.get_connector(tenant)
    assert isinstance(c, connectors.GoogleCalendarConnector)


def test_get_connector_falls_back_to_native_on_bad_config():
    # connector type set but no creds -> _build_google_client raises -> Native fallback
    tenant = {"id": 8, "clinic_data": {"connector": {"type": "google_calendar"}}}
    assert isinstance(connectors.get_connector(tenant), connectors.NativeConnector)
