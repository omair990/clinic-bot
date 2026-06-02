"""Durable staff-notification feed for the bell: persistence, scoping, and unread/seen.
Skips when no DB is reachable (mirrors the other DB-backed integration tests)."""
import uuid

import pytest

from app import db, events


def _db_ok():
    try:
        db.init_db()
        with db.get_conn() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_ok(), reason="no database reachable")


def _tenant():
    sfx = uuid.uuid4().hex[:8]
    return db.create_tenant(f"N {sfx}", f"n-{sfx}", f"PNN{sfx}", None, "Asia/Riyadh", None,
                            {"clinic": {"name": "N"}})


def test_notify_persists_and_lists_for_scope():
    tid = _tenant()
    events.notify("New booking · +966", "Cleaning", level="success", category="booking",
                  tenant_id=tid, link="/conversations/966")
    rows = db.list_notifications(tid)
    assert rows and rows[0]["title"] == "New booking · +966"
    assert rows[0]["category"] == "booking" and rows[0]["link"] == "/conversations/966"


def test_clinic_sees_own_plus_platform_not_other_clinics():
    a, b = _tenant(), _tenant()
    events.notify("For A", category="booking", tenant_id=a)
    events.notify("For B", category="booking", tenant_id=b)
    events.notify("Platform-wide", category="general", tenant_id=None)
    titles_a = {n["title"] for n in db.list_notifications(a)}
    assert "For A" in titles_a and "Platform-wide" in titles_a
    assert "For B" not in titles_a               # another clinic's alert is hidden
    titles_super = {n["title"] for n in db.list_notifications(None)}
    assert {"For A", "For B", "Platform-wide"} <= titles_super   # super sees all


def test_unread_counts_then_seen_clears_durably():
    tid = _tenant()
    db.mark_notifications_seen(tid)               # start from a clean baseline for this viewer
    assert db.notifications_unread(tid) == 0
    events.notify("One", category="booking", tenant_id=tid)
    events.notify("Two", category="no_show", tenant_id=tid)
    assert db.notifications_unread(tid) == 2
    db.mark_notifications_seen(tid)               # opening the bell persists "seen"
    assert db.notifications_unread(tid) == 0      # stays cleared across a fresh read (refresh)
    events.notify("Three", category="review", tenant_id=tid)
    assert db.notifications_unread(tid) == 1      # only the new one is unread


def test_seen_is_per_viewer():
    tid = _tenant()
    events.notify("X", category="booking", tenant_id=tid)
    db.mark_notifications_seen(tid)               # clinic viewer saw it
    # The super-admin is a separate audience and still has it unread.
    assert db.notifications_unread(None) >= 1


def test_missed_visit_sweep_emits_notification():
    import asyncio
    from datetime import datetime, timedelta, timezone
    from app import no_show
    tid = _tenant()
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=3)
    db.upsert_patient(tid, "966missed", "Missed Patient")
    db.create_appointment(tid, "966missed", "Missed Patient", "966missed", "Dr. Hana",
                          "Cleaning", start, start + timedelta(minutes=30))
    # Empty tenants map → no auto WhatsApp send; we only assert the bell notification.
    n = asyncio.run(no_show._detect_no_shows(now, {}))
    assert n >= 1
    titles = [x for x in db.list_notifications(tid) if x["category"] == "no_show"]
    assert titles and "Missed visit" in titles[0]["title"] and titles[0]["link"] == "/no-shows"
