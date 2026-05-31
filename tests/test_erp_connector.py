"""CustomErpConnector logic with a fake ErpApi (no real ERP). Mirror writes hit a real
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


class FakeErp(connectors.ErpApi):
    def __init__(self, slots=None):
        self.slots = slots or []
        self.created = []
        self.rescheduled = []
        self.cancelled = []
        self._seq = 0

    def get_availability(self, doctor, service, on):
        return list(self.slots)

    def create_appointment(self, *, external_ref, doctor, service, patient_name, phone, start, end):
        self._seq += 1
        self.created.append((external_ref, doctor, service, start))
        return f"erp_{self._seq}"

    def reschedule(self, external_id, start, end):
        self.rescheduled.append((external_id, start))

    def cancel(self, external_id):
        self.cancelled.append(external_id)


DOCTOR = {"name": "Dr. E"}
CONF = {"type": "custom_erp", "base_url": "https://erp.example.com/api"}


def _tenant():
    sfx = uuid.uuid4().hex[:8]
    return db.create_tenant(f"E {sfx}", f"e-{sfx}", f"PNE{sfx}", None, "Asia/Riyadh", None,
                            {"clinic": {"name": "E"}})


def test_availability_passthrough_filters_past():
    now = datetime(2026, 6, 8, 12, 0, tzinfo=TZ)
    past = datetime(2026, 6, 8, 9, 0, tzinfo=TZ)
    future = datetime(2026, 6, 8, 15, 0, tzinfo=TZ)
    c = connectors.CustomErpConnector(1, CONF, FakeErp([past, future]))
    slots = c.available_slots(DOCTOR, date(2026, 6, 8), 30, now)
    assert slots == [future]   # ERP's slots, minus anything already past


def test_create_mirrors_and_posts_to_erp():
    tid = _tenant()
    user = "9665" + uuid.uuid4().hex[:7]
    fake = FakeErp()
    c = connectors.CustomErpConnector(tid, CONF, fake)
    now = datetime.now(TZ)
    row = c.create_appointment(wa_user=user, patient_name="Sara", phone="+1", doctor="Dr. E",
                               service="Consult", start=now + timedelta(days=2),
                               end=now + timedelta(days=2, minutes=30))
    assert row.get("external_id") == "erp_1"
    assert fake.created and fake.created[0][0] == str(row["id"])   # external_ref = our id
    assert db.get_appointment(tid, row["id"])["external_id"] == "erp_1"


def test_reschedule_and_cancel_propagate():
    tid = _tenant()
    user = "9665" + uuid.uuid4().hex[:7]
    fake = FakeErp()
    c = connectors.CustomErpConnector(tid, CONF, fake)
    now = datetime.now(TZ)
    row = c.create_appointment(wa_user=user, patient_name="Sara", phone="+1", doctor="Dr. E",
                               service="Consult", start=now + timedelta(days=2),
                               end=now + timedelta(days=2, minutes=30))
    c.reschedule(row["id"], now + timedelta(days=3), now + timedelta(days=3, minutes=30))
    assert fake.rescheduled and fake.rescheduled[0][0] == "erp_1"
    c.set_status(row["id"], "cancelled")
    assert fake.cancelled == ["erp_1"]
    assert db.get_appointment(tid, row["id"])["status"] == "cancelled"


def test_create_keeps_booking_when_erp_errors(monkeypatch):
    tid = _tenant()
    user = "9665" + uuid.uuid4().hex[:7]
    fake = FakeErp()
    monkeypatch.setattr(fake, "create_appointment",
                        lambda **k: (_ for _ in ()).throw(RuntimeError("erp down")))
    c = connectors.CustomErpConnector(tid, CONF, fake)
    now = datetime.now(TZ)
    row = c.create_appointment(wa_user=user, patient_name="Sara", phone="+1", doctor="Dr. E",
                               service="Consult", start=now + timedelta(days=2),
                               end=now + timedelta(days=2, minutes=30))
    assert row["id"] and row.get("external_id") is None
    assert db.get_appointment(tid, row["id"]) is not None


def test_get_connector_dispatches_to_erp(monkeypatch):
    monkeypatch.setattr(connectors, "_build_erp_client", lambda conf: FakeErp())
    tenant = {"id": 11, "clinic_data": {"connector": {"type": "custom_erp",
                                                     "base_url": "https://x"}}}
    assert isinstance(connectors.get_connector(tenant), connectors.CustomErpConnector)


def test_get_connector_falls_back_when_erp_unconfigured():
    tenant = {"id": 12, "clinic_data": {"connector": {"type": "custom_erp"}}}  # no base_url
    assert isinstance(connectors.get_connector(tenant), connectors.NativeConnector)


def test_generic_erp_client_header_auth():
    c = connectors.GenericErpClient(base_url="https://x/", auth={"type": "bearer", "token": "T"})
    assert c._headers()["Authorization"] == "Bearer T"
    c2 = connectors.GenericErpClient(base_url="https://x", auth={"type": "header",
                                                                "name": "X-Key", "value": "K"})
    assert c2._headers()["X-Key"] == "K"
