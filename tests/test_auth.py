"""Tests for staff password hashing."""
from app.auth import hash_password, verify_password


def test_roundtrip():
    h = hash_password("s3cret-pass")
    assert verify_password("s3cret-pass", h)
    assert not verify_password("wrong", h)


def test_rejects_none_and_garbage():
    assert not verify_password("x", None)
    assert not verify_password("x", "not-a-valid-hash")


def test_salted_hashes_differ():
    assert hash_password("same") != hash_password("same")
