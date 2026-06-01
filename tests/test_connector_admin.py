"""Admin connector configuration: the config builder (unit) and the full save/test/mask
flow via the real routes. DB/route tests auto-skip without Postgres."""
import uuid

import pytest

from app import admin, db


# --- _build_connector_config (pure) ---

def test_build_native_clears_connector():
    cfg, err = admin._build_connector_config("native", {}, {})
    assert cfg is None and err is None


def test_build_google_requires_refresh_token():
    cfg, err = admin._build_connector_config("google_calendar", {"g_calendars": "{}"}, {})
    assert cfg is None and "Refresh token" in err


def test_build_keeps_existing_secret_when_blank():
    cfg, err = admin._build_connector_config(
        "google_calendar", {"g_calendars": '{"Dr. A": "cal1"}'}, {"refresh_token": "EXISTING"})
    assert err is None
    assert cfg["refresh_token"] == "EXISTING" and cfg["calendars"] == {"Dr. A": "cal1"}


def test_build_cliniko_validates_required_fields():
    _, err = admin._build_connector_config("cliniko", {"c_api_key": "k"}, {})
    assert "Business id" in err
    cfg, err = admin._build_connector_config("cliniko", {"c_api_key": "k", "c_business_id": "b"}, {})
    assert err is None and cfg["type"] == "cliniko" and cfg["api_key"] == "k"


def test_build_rejects_bad_json_map():
    cfg, err = admin._build_connector_config(
        "cliniko", {"c_api_key": "k", "c_business_id": "b", "c_practitioners": "{bad"}, {})
    assert cfg is None and "invalid JSON" in err


def test_build_erp_and_fhir():
    cfg, err = admin._build_connector_config(
        "custom_erp", {"e_base_url": "https://x", "e_auth_type": "bearer", "e_token": "T"}, {})
    assert err is None and cfg["base_url"] == "https://x" and cfg["auth"]["token"] == "T"
    cfg, err = admin._build_connector_config(
        "fhir", {"f_base_url": "https://f", "f_auth_type": "bearer", "f_token": "T",
                 "f_booking_status": "proposed"}, {})
    assert err is None and cfg["booking_status"] == "proposed" and cfg["auth"]["token"] == "T"


def test_build_includes_webhook_secret_and_keeps_on_blank():
    cfg, err = admin._build_connector_config(
        "cliniko", {"c_api_key": "k", "c_business_id": "b", "webhook_secret": "WS"}, {})
    assert err is None and cfg["webhook_secret"] == "WS"
    cfg, _ = admin._build_connector_config(
        "cliniko", {"c_api_key": "", "c_business_id": "b", "webhook_secret": ""},
        {"api_key": "k", "business_id": "b", "webhook_secret": "OLD"})
    assert cfg["webhook_secret"] == "OLD"          # kept when blank


# --- routes (DB + TestClient) ---

@pytest.fixture
def db_ready():
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
    assert c.post("/api/login", json={"username": "", "password": ADMIN_PASSWORD}).status_code == 200
    return c


def _tenant():
    sfx = uuid.uuid4().hex[:8]
    return db.create_tenant(f"Cfg {sfx}", f"cfg-{sfx}", f"PNCFG{sfx}", None, "Asia/Riyadh", None,
                            {"clinic": {"name": "X"}})


CLINIKO = {"type": "cliniko", "business_id": "biz1", "practitioners": {}, "appointment_types": {}}


def test_connector_api_returns_config(db_ready):
    tid = _tenant()
    body = _super_client().get(f"/api/tenants/{tid}/connector").json()
    assert "config" in body and "secrets_set" in body


def test_save_encrypts_at_rest_and_decrypts_on_read(db_ready):
    tid = _tenant()
    r = _super_client().post(f"/api/tenants/{tid}/connector",
                             json={"config": {**CLINIKO, "api_key": "SECRETKEY"}})
    assert r.status_code == 200
    with db.get_conn() as conn:
        raw = conn.execute("SELECT clinic_data FROM tenants WHERE id=%s", (tid,)).fetchone()
    assert raw["clinic_data"]["connector"]["type"] == "cliniko"
    assert raw["clinic_data"]["connector"]["api_key"].startswith("enc:")   # encrypted at rest
    assert db.get_tenant(tid)["clinic_data"]["connector"]["api_key"] == "SECRETKEY"   # decrypted


def test_save_keeps_existing_secret_on_blank(db_ready):
    tid = _tenant()
    c = _super_client()
    c.post(f"/api/tenants/{tid}/connector", json={"config": {**CLINIKO, "api_key": "FIRST"}})
    c.post(f"/api/tenants/{tid}/connector", json={"config": {**CLINIKO, "api_key": "", "business_id": "biz2"}})
    t = db.get_tenant(tid)
    assert t["clinic_data"]["connector"]["api_key"] == "FIRST"        # kept
    assert t["clinic_data"]["connector"]["business_id"] == "biz2"     # updated


def test_connector_api_masks_stored_secret(db_ready):
    tid = _tenant()
    c = _super_client()
    c.post(f"/api/tenants/{tid}/connector", json={"config": {**CLINIKO, "api_key": "TOPSECRET"}})
    body = c.get(f"/api/tenants/{tid}/connector").json()
    assert body["config"]["api_key"] == "" and "api_key" in body["secrets_set"]


def test_test_native_reports_ok(db_ready):
    tid = _tenant()
    r = _super_client().post(f"/api/tenants/{tid}/connector", json={"config": None, "test": True})
    assert r.status_code == 200 and r.json()["result"]["ok"] is True


def test_test_probes_connector(db_ready, monkeypatch):
    from app import connectors

    class OkClient:
        def ping(self):
            return None

    class BadClient:
        def ping(self):
            raise RuntimeError("401 Unauthorized")

    tid = _tenant()
    c = _super_client()
    monkeypatch.setattr(connectors, "_build_cliniko_client", lambda conf: OkClient())
    r = c.post(f"/api/tenants/{tid}/connector", json={"config": {**CLINIKO, "api_key": "k"}, "test": True})
    assert r.json()["result"]["ok"] is True
    monkeypatch.setattr(connectors, "_build_cliniko_client", lambda conf: BadClient())
    r = c.post(f"/api/tenants/{tid}/connector", json={"config": {**CLINIKO, "api_key": "k"}, "test": True})
    assert r.json()["result"]["ok"] is False and "401" in (r.json()["result"].get("detail") or "")
