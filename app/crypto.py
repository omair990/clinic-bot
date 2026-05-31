"""Application-level encryption for secrets at rest (Fernet / AES-128-CBC + HMAC).

Used to encrypt the per-tenant WhatsApp access token and connector credentials (API keys,
OAuth refresh tokens, bearer tokens) before they touch Postgres, and decrypt them on read —
so a DB dump never exposes live credentials.

Transparent + backward-compatible: encrypted values carry an `enc:` prefix. `decrypt()`
passes through anything without it (legacy plaintext), and `encrypt()` is idempotent
(won't double-encrypt). So this can be rolled out without a hard migration; existing rows
keep working and get encrypted on their next write (plus a one-time sweep in db.init_db).

Key: `SECRETS_KEY` (a Fernet key) if set, else derived from `SECRET_KEY`. NOTE: changing the
key makes existing ciphertext undecryptable — set a stable dedicated `SECRETS_KEY` in prod.
"""
import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.config import SECRET_KEY, SECRETS_KEY

log = logging.getLogger(__name__)

PREFIX = "enc:"
# Secret-bearing keys inside a clinic_data.connector config (top level + nested "auth").
_CONNECTOR_SECRET_KEYS = ("api_key", "refresh_token", "token", "client_secret")
_AUTH_SECRET_KEYS = ("token", "value", "client_secret")

_fernet: Fernet | None = None


def _cipher() -> Fernet:
    global _fernet
    if _fernet is None:
        key = SECRETS_KEY.encode() if SECRETS_KEY else \
            base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest())
        _fernet = Fernet(key)
    return _fernet


def encrypt(value: str | None) -> str | None:
    """Encrypt a string for storage. None/empty pass through; already-encrypted values are
    returned unchanged (idempotent)."""
    if not value or value.startswith(PREFIX):
        return value
    return PREFIX + _cipher().encrypt(value.encode()).decode()


def decrypt(value: str | None) -> str | None:
    """Decrypt a stored string. Values without the prefix (legacy plaintext) pass through."""
    if not value or not value.startswith(PREFIX):
        return value
    try:
        return _cipher().decrypt(value[len(PREFIX):].encode()).decode()
    except InvalidToken:
        log.error("could not decrypt a secret (wrong SECRETS_KEY/SECRET_KEY?)")
        return None


def _map_connector(conn: dict, fn) -> dict:
    out = dict(conn)
    for k in _CONNECTOR_SECRET_KEYS:
        if out.get(k):
            out[k] = fn(out[k])
    auth = out.get("auth")
    if isinstance(auth, dict):
        a = dict(auth)
        for k in _AUTH_SECRET_KEYS:
            if a.get(k):
                a[k] = fn(a[k])
        out["auth"] = a
    return out


def encrypt_clinic_data(cd: dict | None) -> dict | None:
    """Return clinic_data with its connector credentials encrypted (other fields untouched)."""
    if not isinstance(cd, dict) or not isinstance(cd.get("connector"), dict):
        return cd
    return {**cd, "connector": _map_connector(cd["connector"], encrypt)}


def decrypt_clinic_data(cd: dict | None) -> dict | None:
    if not isinstance(cd, dict) or not isinstance(cd.get("connector"), dict):
        return cd
    return {**cd, "connector": _map_connector(cd["connector"], decrypt)}
