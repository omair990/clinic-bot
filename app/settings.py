"""Platform settings: a small DB-backed override layer over environment config, plus a
read-only inventory of all platform env vars for the admin "Settings" page.

Only a curated, runtime-effective subset is editable in the UI (EDITABLE) — e.g. the staff
WhatsApp number, which is read per-request. Most platform config stays in the host env:
secrets that bootstrap the app (DATABASE_URL, SECRET_KEY, …) and LLM provider keys/models
that are read at import time (so a DB value wouldn't take effect without a restart). The
inventory just shows whether each is set, never exposing secret values.
"""
import os

from app import crypto, db

# key -> (label, group). These are safe to manage at runtime and are read via get().
EDITABLE = {
    "ADMIN_WA_NUMBER": ("Staff/owner WhatsApp number (escalations + digests)", "WhatsApp"),
}

# Read-only inventory for the admin page: (key, group, secret?, where_managed).
INVENTORY = [
    ("DATABASE_URL", "Core", True, "env-only (bootstrap)"),
    ("SECRET_KEY", "Core", True, "env-only (bootstrap)"),
    ("SECRETS_KEY", "Core", True, "env-only (encryption key)"),
    ("ADMIN_PASSWORD", "Core", True, "env-only (admin login)"),
    ("WA_ACCESS_TOKEN", "WhatsApp", True, "per-clinic via Connector (encrypted)"),
    ("WA_PHONE_NUMBER_ID", "WhatsApp", False, "per-clinic / env default"),
    ("WA_API_VERSION", "WhatsApp", False, "env (restart)"),
    ("WA_VERIFY_TOKEN", "WhatsApp", True, "env-only (webhook handshake)"),
    ("WA_APP_SECRET", "WhatsApp", True, "env-only (signature check)"),
    ("WA_BUSINESS_ACCOUNT_ID", "WhatsApp", False, "env"),
    ("ADMIN_WA_NUMBER", "WhatsApp", False, "editable here"),
    ("AI_PROVIDERS", "LLM", False, "env (restart)"),
    ("ANTHROPIC_API_KEY", "LLM", True, "env (restart)"),
    ("GEMINI_API_KEY", "LLM", True, "env (restart)"),
    ("GROQ_API_KEY", "LLM", True, "env (restart)"),
    ("MISTRAL_API_KEY", "LLM", True, "env (restart)"),
    ("OPENROUTER_API_KEY", "LLM", True, "env (restart)"),
    ("DEEPSEEK_API_KEY", "LLM", True, "env (restart)"),
    ("CLAUDE_MODEL", "LLM", False, "env (restart)"),
    ("MISTRAL_MODEL", "LLM", False, "env (restart)"),
    ("OPENROUTER_MODEL", "LLM", False, "env (restart)"),
]


def get(key: str, env_default: str | None = None) -> str | None:
    """Effective value: DB override (decrypted if secret) → else env → else the given default."""
    try:
        row = db.get_setting(key)
    except Exception:  # noqa: BLE001 — settings must never break a request
        row = None
    if row and row["value"] is not None:
        return crypto.decrypt(row["value"]) if row["is_secret"] else row["value"]
    return os.environ.get(key, env_default)


def set_value(key: str, value: str | None, is_secret: bool = False) -> None:
    db.upsert_setting(key, crypto.encrypt(value) if (is_secret and value) else value, is_secret)


def inventory_status() -> list[dict]:
    """Per-var status for the read-only admin table. Secret values are never exposed —
    only whether they're set; non-secret values are shown (and DB overrides flagged)."""
    out = []
    for key, group, secret, where in INVENTORY:
        try:
            db_override = db.get_setting(key) is not None
        except Exception:  # noqa: BLE001
            db_override = False
        env_val = os.environ.get(key)
        is_set = bool(env_val) or db_override
        display = ("••••••" if secret else (env_val or "")) if is_set else ""
        out.append({"key": key, "group": group, "secret": secret, "where": where,
                    "is_set": is_set, "display": display, "db_override": db_override})
    return out
