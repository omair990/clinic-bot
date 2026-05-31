"""Regression: editing a clinic must not 500. update_tenant_config writes clinic_data
(a jsonb column) inside COALESCE, which requires the Jsonb adapter — the Json adapter
raised `CannotCoerce: COALESCE could not convert type jsonb to json`, breaking every
clinic edit (and thus setting a clinic's staff password). Requires Postgres; auto-skips.
"""
import uuid

import pytest

from app import db


@pytest.fixture(scope="module")
def tenant():
    try:
        db.init_db()
        if not db.ping():
            pytest.skip("no database reachable")
    except Exception:
        pytest.skip("no database reachable")
    sfx = uuid.uuid4().hex[:8]
    return db.create_tenant(f"Cfg {sfx}", f"cfg-{sfx}", f"PNCFG{sfx}", None,
                            "Asia/Riyadh", None, {"clinic": {"name": "Orig"}})


def test_update_with_clinic_data_dict_persists(tenant):
    db.update_tenant_config(tenant, name="Renamed", wa_phone_number_id=None,
                            wa_access_token=None, timezone="Asia/Riyadh",
                            clinic_data={"clinic": {"name": "Renamed"}, "doctors": []})
    t = db.get_tenant(tenant)
    assert t["name"] == "Renamed"
    assert t["clinic_data"]["clinic"]["name"] == "Renamed"


def test_update_with_none_preserves_existing_clinic_data(tenant):
    db.update_tenant_config(tenant, name="Renamed2", wa_phone_number_id=None,
                            wa_access_token=None, timezone="Asia/Riyadh", clinic_data=None)
    t = db.get_tenant(tenant)
    assert t["name"] == "Renamed2"
    assert t["clinic_data"]["clinic"]["name"] == "Renamed"   # COALESCE kept the prior value


def test_edit_then_set_staff_password(tenant):
    from app.auth import hash_password, verify_password
    # Mirrors the admin edit flow: update config (the part that used to 500) THEN credentials.
    db.update_tenant_config(tenant, name="Renamed3", wa_phone_number_id=None,
                            wa_access_token=None, timezone="Asia/Riyadh",
                            clinic_data={"clinic": {"name": "Renamed3"}})
    uname = "cfg-staff-" + uuid.uuid4().hex[:8]   # staff_username is UNIQUE — keep it per-run
    db.set_tenant_credentials(tenant, uname, hash_password("pw-123"))
    t = db.get_tenant_by_username(uname)
    assert t and t["id"] == tenant
    assert verify_password("pw-123", t["staff_password_hash"])
