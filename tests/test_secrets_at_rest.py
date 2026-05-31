"""Tenant secrets are encrypted in Postgres and transparently decrypted on read.
Requires a real DB; auto-skips otherwise."""
import uuid

import pytest

from app import crypto, db


@pytest.fixture(scope="module", autouse=True)
def _db():
    try:
        db.init_db()
        if not db.ping():
            pytest.skip("no database reachable")
    except Exception:
        pytest.skip("no database reachable")


def _raw(tenant_id):
    with db.get_conn() as conn:
        return conn.execute("SELECT wa_access_token, clinic_data FROM tenants WHERE id = %s",
                            (tenant_id,)).fetchone()


def test_token_and_connector_secrets_encrypted_at_rest_and_decrypted_on_read():
    sfx = uuid.uuid4().hex[:8]
    cd = {"clinic": {"name": "Sec"},
          "connector": {"type": "cliniko", "api_key": "API-SECRET-123", "business_id": "biz1"}}
    tid = db.create_tenant(f"Sec {sfx}", f"sec-{sfx}", f"PNSEC{sfx}", None, "Asia/Riyadh",
                           "WA-TOKEN-XYZ", cd)

    # At rest in Postgres: ciphertext, not the plaintext secrets.
    raw = _raw(tid)
    assert raw["wa_access_token"].startswith("enc:")
    assert "WA-TOKEN-XYZ" not in raw["wa_access_token"]
    assert raw["clinic_data"]["connector"]["api_key"].startswith("enc:")
    assert raw["clinic_data"]["connector"]["business_id"] == "biz1"   # non-secret untouched

    # On read via the app boundary: transparently decrypted.
    t = db.get_tenant(tid)
    assert t["wa_access_token"] == "WA-TOKEN-XYZ"
    assert t["clinic_data"]["connector"]["api_key"] == "API-SECRET-123"

    by_phone = db.get_tenant_by_phone(f"PNSEC{sfx}")
    assert by_phone["wa_access_token"] == "WA-TOKEN-XYZ"


def test_update_re_encrypts_and_reads_back():
    sfx = uuid.uuid4().hex[:8]
    tid = db.create_tenant(f"Sec2 {sfx}", f"sec2-{sfx}", f"PNS2{sfx}", None, "Asia/Riyadh",
                           None, {"clinic": {"name": "S"}})
    db.update_tenant_config(tid, name="S", wa_phone_number_id=f"PNS2{sfx}",
                            wa_access_token="NEW-TOKEN", timezone="Asia/Riyadh",
                            clinic_data={"clinic": {"name": "S"},
                                         "connector": {"type": "fhir", "base_url": "https://x",
                                                       "auth": {"type": "bearer", "token": "T2"}}})
    assert _raw(tid)["wa_access_token"].startswith("enc:")
    assert _raw(tid)["clinic_data"]["connector"]["auth"]["token"].startswith("enc:")
    t = db.get_tenant(tid)
    assert t["wa_access_token"] == "NEW-TOKEN"
    assert t["clinic_data"]["connector"]["auth"]["token"] == "T2"


def test_sweep_encrypts_preexisting_plaintext_token():
    # Simulate a legacy row written before encryption, then run the sweep.
    sfx = uuid.uuid4().hex[:8]
    tid = db.create_tenant(f"Leg {sfx}", f"leg-{sfx}", f"PNLEG{sfx}", None, "Asia/Riyadh",
                           None, {"clinic": {"name": "L"}})
    with db.get_conn() as conn:
        conn.execute("UPDATE tenants SET wa_access_token = %s WHERE id = %s",
                     ("PLAINTEXT-LEGACY", tid))
    db._encrypt_existing_secrets()
    raw = _raw(tid)
    assert raw["wa_access_token"].startswith("enc:")
    assert crypto.decrypt(raw["wa_access_token"]) == "PLAINTEXT-LEGACY"
