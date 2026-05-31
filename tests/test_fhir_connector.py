"""FhirConnector logic with a fake FhirApi (no real FHIR server). Mirror writes hit a real
Postgres; auto-skips without one."""
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


class FakeFhir(connectors.FhirApi):
    def __init__(self, slots=None):
        self.slots = slots or []
        self.created = []
        self.updated = []
        self.cancelled = []
        self._seq = 0

    def free_slots(self, schedule_ref, time_min, time_max):
        return list(self.slots)

    def find_or_create_patient(self, name, phone):
        return f"Patient/{phone}"

    def create_appointment(self, *, practitioner_ref, patient_ref, start, end, status):
        self._seq += 1
        self.created.append((practitioner_ref, patient_ref, start, status))
        return f"appt_{self._seq}"

    def update_appointment(self, appointment_id, start, end):
        self.updated.append((appointment_id, start))

    def cancel_appointment(self, appointment_id):
        self.cancelled.append(appointment_id)


DOCTOR = {"name": "Dr. H"}
CONF = {"type": "fhir", "base_url": "https://fhir.h.org/r4",
        "schedules": {"Dr. H": "Schedule/1"}, "practitioners": {"Dr. H": "Practitioner/9"}}


def _tenant():
    sfx = uuid.uuid4().hex[:8]
    return db.create_tenant(f"F {sfx}", f"f-{sfx}", f"PNF{sfx}", None, "Asia/Riyadh", None,
                            {"clinic": {"name": "F"}})


def test_availability_from_free_slots_filters_past():
    now = datetime(2026, 6, 8, 12, 0, tzinfo=TZ)
    past = datetime(2026, 6, 8, 9, 0, tzinfo=TZ)
    future = datetime(2026, 6, 8, 15, 0, tzinfo=TZ)
    c = connectors.FhirConnector(1, CONF, FakeFhir([past, future]))
    assert c.available_slots(DOCTOR, date(2026, 6, 8), 30, now) == [future]


def test_no_schedule_mapping_yields_no_slots():
    c = connectors.FhirConnector(1, {"schedules": {}}, FakeFhir([datetime(2026, 6, 8, 15, tzinfo=TZ)]))
    assert c.available_slots(DOCTOR, date(2026, 6, 8), 30,
                             datetime(2026, 6, 7, 9, tzinfo=TZ)) == []


def test_create_books_and_mirrors_default_status():
    tid = _tenant()
    user = "9665" + uuid.uuid4().hex[:7]
    fake = FakeFhir()
    c = connectors.FhirConnector(tid, CONF, fake)
    now = datetime.now(TZ)
    row = c.create_appointment(wa_user=user, patient_name="Sara", phone="+1", doctor="Dr. H",
                               service="Consult", start=now + timedelta(days=2),
                               end=now + timedelta(days=2, minutes=30))
    assert row["external_id"] == "appt_1"
    assert fake.created[0][0] == "Practitioner/9" and fake.created[0][3] == "booked"
    assert not row.get("pending")
    assert db.get_appointment(tid, row["id"])["external_id"] == "appt_1"


def test_create_request_to_book_marks_pending():
    tid = _tenant()
    user = "9665" + uuid.uuid4().hex[:7]
    fake = FakeFhir()
    conf = {**CONF, "booking_status": "proposed"}
    c = connectors.FhirConnector(tid, conf, fake)
    now = datetime.now(TZ)
    row = c.create_appointment(wa_user=user, patient_name="Sara", phone="+1", doctor="Dr. H",
                               service="Consult", start=now + timedelta(days=2),
                               end=now + timedelta(days=2, minutes=30))
    assert fake.created[0][3] == "proposed" and row.get("pending") is True


def test_reschedule_and_cancel_propagate():
    tid = _tenant()
    user = "9665" + uuid.uuid4().hex[:7]
    fake = FakeFhir()
    c = connectors.FhirConnector(tid, CONF, fake)
    now = datetime.now(TZ)
    row = c.create_appointment(wa_user=user, patient_name="Sara", phone="+1", doctor="Dr. H",
                               service="Consult", start=now + timedelta(days=2),
                               end=now + timedelta(days=2, minutes=30))
    c.reschedule(row["id"], now + timedelta(days=3), now + timedelta(days=3, minutes=30))
    assert fake.updated and fake.updated[0][0] == "appt_1"
    c.set_status(row["id"], "cancelled")
    assert fake.cancelled == ["appt_1"]
    assert db.get_appointment(tid, row["id"])["status"] == "cancelled"


def test_create_keeps_booking_when_fhir_errors(monkeypatch):
    tid = _tenant()
    user = "9665" + uuid.uuid4().hex[:7]
    fake = FakeFhir()
    monkeypatch.setattr(fake, "create_appointment",
                        lambda **k: (_ for _ in ()).throw(RuntimeError("fhir 500")))
    c = connectors.FhirConnector(tid, CONF, fake)
    now = datetime.now(TZ)
    row = c.create_appointment(wa_user=user, patient_name="Sara", phone="+1", doctor="Dr. H",
                               service="Consult", start=now + timedelta(days=2),
                               end=now + timedelta(days=2, minutes=30))
    assert row["id"] and row.get("external_id") is None
    assert db.get_appointment(tid, row["id"]) is not None


def test_get_connector_dispatches_to_fhir(monkeypatch):
    monkeypatch.setattr(connectors, "_build_fhir_client", lambda conf: FakeFhir())
    tenant = {"id": 13, "clinic_data": {"connector": {"type": "fhir", "base_url": "https://x"}}}
    assert isinstance(connectors.get_connector(tenant), connectors.FhirConnector)


def test_get_connector_falls_back_when_fhir_unconfigured():
    tenant = {"id": 14, "clinic_data": {"connector": {"type": "fhir"}}}  # no base_url
    assert isinstance(connectors.get_connector(tenant), connectors.NativeConnector)
