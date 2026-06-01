"""JSON API (/api/*) for the React console: auth matrix, read endpoints, role scoping.
Requires Postgres (skips otherwise)."""
import uuid

import pytest

from app import db
from app.auth import hash_password
from app.config import ADMIN_PASSWORD


@pytest.fixture(scope="module", autouse=True)
def _db():
    try:
        db.init_db()
        if not db.ping():
            pytest.skip("no database reachable")
    except Exception:
        pytest.skip("no database reachable")


def _client():
    from fastapi.testclient import TestClient
    import main
    return TestClient(main.app)


def _super():
    c = _client()
    assert c.post("/api/login", json={"username": "", "password": ADMIN_PASSWORD}).status_code == 200
    return c


def _clinic():
    tid = db.create_tenant(f"Api {uuid.uuid4().hex[:6]}", f"api-{uuid.uuid4().hex[:6]}",
                           None, 1, "Asia/Riyadh", None, {"clinic": {"name": "X"}})
    uname = "apistaff-" + uuid.uuid4().hex[:8]
    db.set_tenant_credentials(tid, uname, hash_password("pw"))
    c = _client()
    assert c.post("/api/login", json={"username": uname, "password": "pw"}).status_code == 200
    return c, tid


def test_login_bad_credentials_401():
    assert _client().post("/api/login", json={"username": "", "password": "wrong"}).status_code == 401


def test_unauthenticated_endpoints_401():
    c = _client()
    for p in ("/me", "/overview", "/dashboard", "/conversations", "/appointments", "/plans"):
        assert c.get("/api" + p).status_code == 401, p


def test_super_read_endpoints_ok():
    c = _super()
    assert c.get("/api/me").json()["role"] == "super"
    for p in ("/overview", "/dashboard", "/clinics", "/conversations", "/appointments",
              "/reviews", "/no-shows", "/plans", "/logs", "/settings"):
        assert c.get("/api" + p).status_code == 200, p


def test_clinic_role_scoping():
    c, _ = _clinic()
    assert c.get("/api/me").json()["role"] == "clinic"
    assert c.get("/api/dashboard").status_code == 200
    assert c.get("/api/usage").status_code == 200
    # super-only endpoints are forbidden for a clinic login
    for p in ("/overview", "/plans", "/logs", "/settings", "/tenants/1"):
        assert c.get("/api" + p).status_code == 403, p


def test_logout_clears_session():
    c = _super()
    assert c.get("/api/me").status_code == 200
    c.post("/api/logout")
    assert c.get("/api/me").status_code == 401


def test_create_rejects_invalid_clinic_data():
    c = _super()
    # a doctor missing required schema fields must be rejected (not silently saved)
    r = c.post("/api/tenants", json={"name": "Bad", "slug": "bad-" + uuid.uuid4().hex[:6],
               "plan_id": 1, "clinic_data": '{"doctors":[{"name":"Dr. X"}]}'})
    assert r.status_code == 400 and "Clinic data invalid" in r.json()["detail"]
