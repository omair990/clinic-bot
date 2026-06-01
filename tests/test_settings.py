"""Platform settings store (DB override + env fallback + encryption) and the admin page.
Requires Postgres; auto-skips otherwise."""
import uuid

import pytest

from app import db, settings


@pytest.fixture(scope="module", autouse=True)
def _db():
    try:
        db.init_db()
        if not db.ping():
            pytest.skip("no database reachable")
    except Exception:
        pytest.skip("no database reachable")


def test_db_override_beats_env():
    settings.set_value("ADMIN_WA_NUMBER", "966500000111")
    assert settings.get("ADMIN_WA_NUMBER", "fallback") == "966500000111"


def test_env_default_when_unset():
    assert settings.get("UNSET_KEY_" + uuid.uuid4().hex, "deflt") == "deflt"


def test_secret_setting_encrypted_at_rest_and_decrypted():
    k = "TEST_SECRET_" + uuid.uuid4().hex[:6]
    settings.set_value(k, "s3cr3t", is_secret=True)
    raw = db.get_setting(k)
    assert raw["is_secret"] and raw["value"].startswith("enc:") and "s3cr3t" not in raw["value"]
    assert settings.get(k) == "s3cr3t"


def test_inventory_never_exposes_secret_values():
    inv = {s["key"]: s for s in settings.inventory_status()}
    assert "DATABASE_URL" in inv and inv["DATABASE_URL"]["secret"] and inv["DATABASE_URL"]["is_set"]
    assert inv["DATABASE_URL"]["display"] == "••••••"          # secret value masked, not shown
    assert "ADMIN_WA_NUMBER" in inv


def _super_client():
    from fastapi.testclient import TestClient
    from app.config import ADMIN_PASSWORD
    import main
    c = TestClient(main.app)
    assert c.post("/api/login", json={"username": "", "password": ADMIN_PASSWORD}).status_code == 200
    return c


def test_settings_api_returns_editable_and_inventory():
    r = _super_client().get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    assert "ADMIN_WA_NUMBER" in body["editable"] and "inventory" in body


def test_settings_save_updates_editable_value():
    c = _super_client()
    r = c.post("/api/settings", json={"values": {"ADMIN_WA_NUMBER": "966500009999"}})
    assert r.status_code == 200
    assert settings.get("ADMIN_WA_NUMBER") == "966500009999"
    # and the inventory flags it as a DB override now
    inv = {s["key"]: s for s in settings.inventory_status()}
    assert inv["ADMIN_WA_NUMBER"]["db_override"] is True
