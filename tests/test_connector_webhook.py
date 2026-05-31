"""Inbound connector webhook: reconciliation logic + the authenticated route.
Requires Postgres; auto-skips otherwise."""
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


def _tenant(secret="WHSEC"):
    sfx = uuid.uuid4().hex[:8]
    return db.create_tenant(f"Hk {sfx}", f"hk-{sfx}", f"PNHK{sfx}", None, "Asia/Riyadh", None,
                            {"clinic": {"name": "H"},
                             "connector": {"type": "cliniko", "api_key": "k", "business_id": "b",
                                           "webhook_secret": secret}})


def _client():
    from fastapi.testclient import TestClient
    import main
    return TestClient(main.app)


def _iso(dt):
    return dt.isoformat()


# --- reconciliation logic ---

def test_apply_created_then_updated_then_cancelled():
    tid = _tenant()
    now = datetime.now(TZ)
    assert connectors.apply_inbound_event(tid, {
        "event": "created", "external_id": "X1", "wa_user": "96650", "doctor": "Dr. A",
        "service": "Consult", "start": _iso(now + timedelta(days=2)),
        "end": _iso(now + timedelta(days=2, minutes=30))}) == "created"
    a = db.appointment_by_external_id(tid, "X1")
    assert a and a["status"] == "confirmed" and a["wa_user"] == "96650"

    assert connectors.apply_inbound_event(tid, {
        "event": "updated", "external_id": "X1", "start": _iso(now + timedelta(days=3)),
        "end": _iso(now + timedelta(days=3, minutes=30))}) == "updated"
    assert db.appointment_by_external_id(tid, "X1")["start_at"].date() == (now + timedelta(days=3)).date()

    assert connectors.apply_inbound_event(tid, {"event": "cancelled", "external_id": "X1"}) == "status:cancelled"
    assert db.appointment_by_external_id(tid, "X1")["status"] == "cancelled"


def test_apply_ignores_unknown_and_incomplete():
    tid = _tenant()
    assert connectors.apply_inbound_event(tid, {"event": "cancelled", "external_id": "NOPE"}) == "ignored:unknown_appointment"
    assert connectors.apply_inbound_event(tid, {"event": "created"}) == "ignored:no_external_id"
    assert connectors.apply_inbound_event(tid, {"event": "created", "external_id": "Z"}) == "ignored:incomplete"


# --- the route ---

def test_webhook_rejects_missing_or_wrong_token():
    tid = _tenant()
    c = _client()
    body = {"event": "cancelled", "external_id": "Y1"}
    assert c.post(f"/connector/{tid}/webhook", json=body).status_code == 401
    assert c.post(f"/connector/{tid}/webhook", json=body,
                  headers={"X-Connector-Token": "WRONG"}).status_code == 401


def test_webhook_unknown_tenant_404():
    c = _client()
    r = c.post("/connector/99999999/webhook", json={"event": "created"},
               headers={"X-Connector-Token": "x"})
    assert r.status_code == 404


def test_webhook_creates_and_is_idempotent():
    tid = _tenant()
    c = _client()
    now = datetime.now(TZ)
    body = {"event": "created", "event_id": "evt-1", "external_id": "Y2", "wa_user": "96652",
            "doctor": "Dr. A", "service": "Consult", "start": _iso(now + timedelta(days=2)),
            "end": _iso(now + timedelta(days=2, minutes=30))}
    r = c.post(f"/connector/{tid}/webhook", json=body, headers={"X-Connector-Token": "WHSEC"})
    assert r.status_code == 200 and r.json()["status"] == "created"
    assert db.appointment_by_external_id(tid, "Y2") is not None

    r2 = c.post(f"/connector/{tid}/webhook", json=body, headers={"X-Connector-Token": "WHSEC"})
    assert r2.json()["status"] == "duplicate"                     # same event_id -> no-op
    with db.get_conn() as conn:
        n = conn.execute("SELECT COUNT(*) AS n FROM appointments WHERE tenant_id=%s "
                         "AND external_id='Y2'", (tid,)).fetchone()["n"]
    assert n == 1                                                  # not double-created


def test_webhook_cancel_updates_mirror():
    tid = _tenant()
    c = _client()
    now = datetime.now(TZ)
    db.create_mirror_appointment(tid, "Y3", "96653", "P", "+1", "Dr. A", "Consult",
                                 now + timedelta(days=2), now + timedelta(days=2, minutes=30))
    r = c.post(f"/connector/{tid}/webhook",
               json={"event": "cancelled", "external_id": "Y3"},
               headers={"X-Connector-Token": "WHSEC"})
    assert r.status_code == 200 and r.json()["status"] == "status:cancelled"
    assert db.appointment_by_external_id(tid, "Y3")["status"] == "cancelled"
