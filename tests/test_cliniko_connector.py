"""ClinikoConnector logic, exercised with a fake ClinikoApi (no real Cliniko).
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


class FakeCliniko(connectors.ClinikoApi):
    def __init__(self, busy=None):
        self.busy = busy or []
        self.patients = {}
        self.created = []
        self.updated = []
        self.cancelled = []
        self._seq = 0

    def list_busy(self, practitioner_id, time_min, time_max):
        return [b for b in self.busy if b[0] >= time_min and b[1] <= time_max]

    def find_or_create_patient(self, name, phone):
        self.patients.setdefault(phone, f"pat_{phone}")
        return self.patients[phone]

    def create_appointment(self, *, business_id, practitioner_id, appointment_type_id,
                           patient_id, start, end):
        self._seq += 1
        self.created.append((business_id, practitioner_id, appointment_type_id, patient_id, start))
        return f"cl_{self._seq}"

    def update_appointment(self, appointment_id, start, end):
        self.updated.append((appointment_id, start))

    def cancel_appointment(self, appointment_id):
        self.cancelled.append(appointment_id)


DOCTOR = {"name": "Dr. K", "specialty": "gp",
          "available_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                             "Saturday", "Sunday"],
          "available_hours": "9:00 AM - 5:00 PM"}

CONF = {"type": "cliniko", "business_id": "biz1",
        "practitioners": {"Dr. K": "pr1"}, "appointment_types": {"Consult": "at1"}}


def _tenant():
    sfx = uuid.uuid4().hex[:8]
    return db.create_tenant(f"CK {sfx}", f"ck-{sfx}", f"PNCK{sfx}", None, "Asia/Riyadh", None,
                            {"clinic": {"name": "CK"}})


def test_capabilities():
    assert connectors.CREATE in connectors.ClinikoConnector(1, CONF, FakeCliniko()).capabilities()


def test_availability_uses_cliniko_busy():
    on = date(2026, 6, 8)   # Monday
    busy = [(datetime(2026, 6, 8, 13, 0, tzinfo=TZ), datetime(2026, 6, 8, 14, 0, tzinfo=TZ))]
    c = connectors.ClinikoConnector(1, CONF, FakeCliniko(busy))
    slots = {s.strftime("%H:%M") for s in
             c.available_slots(DOCTOR, on, 30, datetime(2026, 6, 7, 9, 0, tzinfo=TZ))}
    assert "12:00" in slots and "13:00" not in slots and "13:30" not in slots


def test_unmapped_practitioner_returns_no_slots():
    c = connectors.ClinikoConnector(1, {"practitioners": {}}, FakeCliniko())
    assert c.available_slots(DOCTOR, date(2026, 6, 8), 30,
                             datetime(2026, 6, 7, 9, 0, tzinfo=TZ)) == []


def test_create_mirrors_and_books_in_cliniko():
    tid = _tenant()
    user = "9665" + uuid.uuid4().hex[:7]
    fake = FakeCliniko()
    c = connectors.ClinikoConnector(tid, CONF, fake)
    now = datetime.now(TZ)
    row = c.create_appointment(wa_user=user, patient_name="Sara Ali", phone="+1", doctor="Dr. K",
                               service="Consult", start=now + timedelta(days=2),
                               end=now + timedelta(days=2, minutes=30))
    assert row.get("external_id") == "cl_1"
    assert fake.created and fake.created[0][1] == "pr1" and fake.created[0][2] == "at1"
    assert db.get_appointment(tid, row["id"])["external_id"] == "cl_1"


def test_reschedule_and_cancel_propagate():
    tid = _tenant()
    user = "9665" + uuid.uuid4().hex[:7]
    fake = FakeCliniko()
    c = connectors.ClinikoConnector(tid, CONF, fake)
    now = datetime.now(TZ)
    row = c.create_appointment(wa_user=user, patient_name="Sara", phone="+1", doctor="Dr. K",
                               service="Consult", start=now + timedelta(days=2),
                               end=now + timedelta(days=2, minutes=30))
    c.reschedule(row["id"], now + timedelta(days=3), now + timedelta(days=3, minutes=30))
    assert fake.updated and fake.updated[0][0] == "cl_1"
    c.set_status(row["id"], "cancelled")
    assert fake.cancelled == ["cl_1"]
    assert db.get_appointment(tid, row["id"])["status"] == "cancelled"


def test_create_keeps_booking_when_cliniko_errors(monkeypatch):
    tid = _tenant()
    user = "9665" + uuid.uuid4().hex[:7]
    fake = FakeCliniko()
    monkeypatch.setattr(fake, "create_appointment",
                        lambda **k: (_ for _ in ()).throw(RuntimeError("cliniko 500")))
    c = connectors.ClinikoConnector(tid, CONF, fake)
    now = datetime.now(TZ)
    row = c.create_appointment(wa_user=user, patient_name="Sara", phone="+1", doctor="Dr. K",
                               service="Consult", start=now + timedelta(days=2),
                               end=now + timedelta(days=2, minutes=30))
    assert row["id"] and row.get("external_id") is None
    assert db.get_appointment(tid, row["id"]) is not None


def test_get_connector_dispatches_to_cliniko(monkeypatch):
    fake = FakeCliniko()
    monkeypatch.setattr(connectors, "_build_cliniko_client", lambda conf: fake)
    tenant = {"id": 9, "clinic_data": {"connector": {"type": "cliniko", "api_key": "k-au1"}}}
    assert isinstance(connectors.get_connector(tenant), connectors.ClinikoConnector)


def test_get_connector_falls_back_when_cliniko_unconfigured():
    tenant = {"id": 10, "clinic_data": {"connector": {"type": "cliniko"}}}  # no api_key
    assert isinstance(connectors.get_connector(tenant), connectors.NativeConnector)
