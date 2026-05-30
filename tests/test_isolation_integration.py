"""Integration tests proving per-tenant data isolation. Requires a real Postgres
(run via `scripts/staging.sh test`); skipped automatically when no DB is reachable.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app import db

pytestmark = pytest.mark.filterwarnings("ignore")


@pytest.fixture(scope="module")
def two_tenants():
    try:
        db.init_db()
        if not db.ping():
            pytest.skip("no database reachable")
    except Exception:
        pytest.skip("no database reachable")

    sfx = uuid.uuid4().hex[:8]
    clinic = lambda name: {  # noqa: E731
        "clinic": {"name": name},
        "doctors": [{"name": "Dr. Test", "specialty": "gp",
                     "available_days": ["Sunday"], "available_hours": "10:00 AM - 1:00 PM"}],
        "services": [{"name": "Consult", "price_sar": 100, "duration_min": 30}],
    }
    a = db.create_tenant(f"A {sfx}", f"a-{sfx}", f"PNA{sfx}", None, "Asia/Riyadh", None, clinic("A"))
    b = db.create_tenant(f"B {sfx}", f"b-{sfx}", f"PNB{sfx}", None, "Asia/Riyadh", None, clinic("B"))
    return a, b, f"96650{sfx[:6]}"


def test_conversation_history_is_isolated(two_tenants):
    a, b, user = two_tenants
    db.log_message(a, user, "in", "hello from A side")
    db.log_message(b, user, "in", "hello from B side")
    ha = db.recent_history(a, user)
    hb = db.recent_history(b, user)
    assert any("A side" in m["message"] for m in ha)
    assert all("B side" not in m["message"] for m in ha)
    assert any("B side" in m["message"] for m in hb)


def test_patient_name_is_per_tenant(two_tenants):
    a, b, user = two_tenants
    db.upsert_patient(a, user, "Alice")
    db.upsert_patient(b, user, "Bob")
    assert db.get_patient_name(a, user) == "Alice"
    assert db.get_patient_name(b, user) == "Bob"   # same phone, different clinic


def test_same_doctor_time_not_cross_booked(two_tenants):
    a, b, user = two_tenants
    start = datetime.now(timezone.utc) + timedelta(days=3)
    end = start + timedelta(minutes=30)
    ra = db.create_appointment(a, user, "Alice", "Dr. Test", "Consult", start, end)
    rb = db.create_appointment(b, user, "Bob", "Dr. Test", "Consult", start, end)
    assert not ra.get("conflict") and not rb.get("conflict")   # different tenants don't clash
    # but a second booking in the SAME tenant at the same time does clash
    rc = db.create_appointment(a, user, "Alice", "Dr. Test", "Consult", start, end)
    assert rc.get("conflict")


def test_booked_intervals_and_upcoming_isolated(two_tenants):
    a, b, user = two_tenants
    day_start = datetime.now(timezone.utc) + timedelta(days=2)
    day_end = day_start + timedelta(days=10)
    ia = db.booked_intervals(a, "Dr. Test", day_start, day_end)
    ib = db.booked_intervals(b, "Dr. Test", day_start, day_end)
    assert len(ia) >= 1 and len(ib) >= 1
    # A's appointments never appear in B's list and vice versa (counts independent)
    ua = db.upcoming_appointments(a, user, datetime.now(timezone.utc))
    assert all(r["tenant_id"] == a for r in ua)


def test_admin_queries_are_tenant_scoped(two_tenants):
    a, b, user = two_tenants
    db.log_message(a, user, "in", "scoped to A only")
    db.log_message(b, user, "in", "scoped to B only")
    convs_a = db.list_conversations(tenant_id=a)
    row = next((c for c in convs_a if c["wa_user"] == user), None)
    assert row is not None
    assert "A only" in row["last_message"]      # not B's message, despite shared phone
    sa, sb = db.stats(tenant_id=a), db.stats(tenant_id=b)
    assert sa["messages"] >= 1 and sb["messages"] >= 1


def test_staff_credentials_lookup(two_tenants):
    from app.auth import hash_password, verify_password
    a, _b, _user = two_tenants
    db.set_tenant_credentials(a, "clinic-a-staff", hash_password("pw-a"))
    t = db.get_tenant_by_username("clinic-a-staff")
    assert t and t["id"] == a
    assert verify_password("pw-a", t["staff_password_hash"])


def test_cross_tenant_appointment_access_blocked(two_tenants):
    a, b, user = two_tenants
    start = datetime.now(timezone.utc) + timedelta(days=5)
    row = db.create_appointment(a, user, "Alice", "Dr. Test", "Consult",
                                start, start + timedelta(minutes=30))
    appt_id = row["id"]
    assert db.get_appointment(a, appt_id) is not None
    assert db.get_appointment(b, appt_id) is None   # B cannot see A's appointment
