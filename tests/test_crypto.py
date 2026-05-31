"""Unit tests for secrets-at-rest encryption (no DB)."""
from app import crypto


def test_roundtrip_and_prefix():
    enc = crypto.encrypt("super-secret-token")
    assert enc.startswith("enc:") and enc != "super-secret-token"
    assert crypto.decrypt(enc) == "super-secret-token"


def test_encrypt_is_idempotent():
    once = crypto.encrypt("k")
    assert crypto.encrypt(once) == once          # already encrypted -> unchanged


def test_decrypt_passes_through_legacy_plaintext():
    assert crypto.decrypt("legacy-plaintext") == "legacy-plaintext"


def test_none_and_empty_pass_through():
    assert crypto.encrypt(None) is None and crypto.encrypt("") == ""
    assert crypto.decrypt(None) is None and crypto.decrypt("") == ""


def test_connector_secrets_encrypted_and_recovered():
    cd = {"clinic": {"name": "X"}, "doctors": [{"name": "Dr. A"}],
          "connector": {"type": "cliniko", "api_key": "AK", "business_id": "biz1",
                        "auth": {"type": "bearer", "token": "TKN"}}}
    enc = crypto.encrypt_clinic_data(cd)
    # secrets encrypted...
    assert enc["connector"]["api_key"].startswith("enc:")
    assert enc["connector"]["auth"]["token"].startswith("enc:")
    # ...non-secret fields untouched
    assert enc["connector"]["business_id"] == "biz1"
    assert enc["clinic"] == cd["clinic"] and enc["doctors"] == cd["doctors"]
    # round-trips
    back = crypto.decrypt_clinic_data(enc)
    assert back["connector"]["api_key"] == "AK" and back["connector"]["auth"]["token"] == "TKN"


def test_clinic_data_without_connector_unchanged():
    cd = {"clinic": {"name": "X"}}
    assert crypto.encrypt_clinic_data(cd) == cd
    assert crypto.decrypt_clinic_data(cd) == cd
