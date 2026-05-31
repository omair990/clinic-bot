"""Connector layer: NativeConnector round-trip + factory. DB-backed; auto-skips without PG."""
import uuid
from datetime import datetime, timedelta

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


def test_get_connector_is_native_with_full_capabilities():
    c = connectors.get_connector({"id": 1})
    assert isinstance(c, connectors.NativeConnector)
    assert c.capabilities() == {connectors.READ_AVAILABILITY, connectors.CREATE,
                                connectors.RESCHEDULE, connectors.CANCEL, connectors.LIST}


def test_native_connector_create_list_reschedule_cancel_roundtrip():
    sfx = uuid.uuid4().hex[:8]
    tid = db.create_tenant(f"Conn {sfx}", f"conn-{sfx}", f"PNC{sfx}", None,
                           "Asia/Riyadh", None, {"clinic": {"name": "C"}})
    user = "9665" + uuid.uuid4().hex[:7]
    conn = connectors.NativeConnector(tid)
    now = datetime.now(TZ)
    start, end = now + timedelta(days=2), now + timedelta(days=2, minutes=30)

    row = conn.create_appointment(wa_user=user, patient_name="P", phone="+1", doctor="Dr. C",
                                  service="Consult", start=start, end=end)
    assert row["id"] and not row.get("conflict")
    appt_id = row["id"]

    assert conn.get_appointment(appt_id)["wa_user"] == user
    assert any(a["id"] == appt_id for a in conn.upcoming_appointments(user, now))

    new_start = now + timedelta(days=3)
    moved = conn.reschedule(appt_id, new_start, new_start + timedelta(minutes=30))
    assert not moved.get("conflict") and moved["start_at"].date() == new_start.date()

    conn.set_status(appt_id, "cancelled")
    assert conn.get_appointment(appt_id)["status"] == "cancelled"


def test_native_connector_create_detects_conflict():
    sfx = uuid.uuid4().hex[:8]
    tid = db.create_tenant(f"Conn2 {sfx}", f"conn2-{sfx}", f"PND{sfx}", None,
                           "Asia/Riyadh", None, {"clinic": {"name": "C"}})
    conn = connectors.NativeConnector(tid)
    now = datetime.now(TZ)
    start, end = now + timedelta(days=2), now + timedelta(days=2, minutes=30)
    assert conn.create_appointment(wa_user="9651", patient_name="A", phone="+1", doctor="Dr. X",
                                   service="Consult", start=start, end=end)["id"]
    clash = conn.create_appointment(wa_user="9652", patient_name="B", phone="+2", doctor="Dr. X",
                                    service="Consult", start=start, end=end)
    assert clash.get("conflict") is True
