"""Named platform-admin logins (ADMIN_ACCOUNTS). Requires Postgres; auto-skips otherwise."""
import pytest

from app import db


@pytest.fixture(scope="module", autouse=True)
def _db():
    try:
        db.init_db()
        if not db.ping():
            pytest.skip("no database reachable")
    except Exception:
        pytest.skip("no database reachable")


def _client(monkeypatch):
    from fastapi.testclient import TestClient
    from app import api
    monkeypatch.setattr(api, "ADMIN_ACCOUNTS", {"manager": "Riyadh-2026"})
    import main
    return TestClient(main.app)


def test_named_admin_logs_in_as_super(monkeypatch):
    c = _client(monkeypatch)
    r = c.post("/api/login", json={"username": "manager", "password": "Riyadh-2026"})
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "super" and body["tenant_id"] is None
    # the session truly has super powers (a super-only endpoint works)
    assert c.get("/api/plans").status_code == 200


def test_named_admin_wrong_password_rejected(monkeypatch):
    c = _client(monkeypatch)
    assert c.post("/api/login", json={"username": "manager", "password": "nope"}).status_code == 401


def test_unknown_admin_username_rejected(monkeypatch):
    c = _client(monkeypatch)
    assert c.post("/api/login", json={"username": "ghost", "password": "Riyadh-2026"}).status_code == 401
