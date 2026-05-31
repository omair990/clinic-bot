"""Delete-tenant route + db.delete_tenant, including the safety gate. Requires Postgres."""
import uuid

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


def _super_client():
    from fastapi.testclient import TestClient
    from app.config import ADMIN_PASSWORD
    import main
    c = TestClient(main.app)
    assert c.post("/admin/login", data={"username": "", "password": ADMIN_PASSWORD},
                  follow_redirects=False).status_code == 303
    return c


def _make_tenant():
    slug = "deltest-" + uuid.uuid4().hex[:8]
    tid = db.create_tenant(f"Del Test {slug}", slug, None, 1, "Asia/Riyadh", None,
                           {"clinic": {"name": "Del"}})
    return tid, slug


def test_default_tenant_cannot_be_deleted():
    default = db.get_default_tenant()
    assert default, "expected a seeded default tenant"
    c = _super_client()
    r = c.post(f"/admin/tenants/{default['id']}/delete",
               data={"confirm_slug": default.get("slug") or "default"},
               follow_redirects=False)
    assert r.status_code == 403
    assert db.get_tenant(default["id"]) is not None      # still there


def test_wrong_slug_is_rejected_and_tenant_survives():
    tid, slug = _make_tenant()
    c = _super_client()
    r = c.post(f"/admin/tenants/{tid}/delete", data={"confirm_slug": "not-the-slug"},
               follow_redirects=False)
    assert r.status_code == 400
    assert db.get_tenant(tid) is not None
    db.delete_tenant(tid)  # cleanup


def test_delete_removes_tenant_and_its_children():
    tid, slug = _make_tenant()
    # give it a child row in a tenant-scoped table
    db.log_message(tid, "966500000000", "in", "hello")
    assert db.recent_history(tid, "966500000000"), "precondition: message logged"

    c = _super_client()
    r = c.post(f"/admin/tenants/{tid}/delete", data={"confirm_slug": slug},
               follow_redirects=False)
    assert r.status_code == 303
    assert db.get_tenant(tid) is None                    # tenant gone
    assert db.recent_history(tid, "966500000000") == []  # child rows gone


def test_db_delete_tenant_is_idempotent_on_missing():
    # deleting a non-existent tenant clears nothing and does not raise
    cleared = db.delete_tenant(999999999)
    assert isinstance(cleared, int)
