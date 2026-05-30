"""Tenant resolution + usage metering.

Phase 1: identify the tenant for an inbound message (by WhatsApp phone_number_id,
falling back to the default tenant) and count text/voice usage per calendar month.
Quota *enforcement* is layered on in a later phase; counting is always safe.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app import db

log = logging.getLogger(__name__)

# Patient-facing messages when a clinic's plan blocks a message.
MSG_UNAVAILABLE = ("Sorry, this service is currently unavailable. "
                   "Please contact the clinic directly.")
MSG_VOICE_OFF = ("Sorry, voice messages aren't available right now — "
                 "please type your message and I'll help. 🙏")
MSG_QUOTA = ("Sorry, we've reached our messaging limit for now. "
             "Please contact the clinic directly or try again later.")


@dataclass
class Decision:
    allowed: bool
    reason: str | None = None     # suspended | expired | trial_expired | voice_not_allowed | text_quota | voice_quota
    message: str | None = None    # patient-facing text when blocked


def current_period(tz: str = "Asia/Riyadh") -> str:
    """Billing period bucket, 'YYYY-MM', in the tenant's timezone."""
    try:
        now = datetime.now(ZoneInfo(tz))
    except Exception:  # noqa: BLE001 — bad tz string shouldn't break metering
        now = datetime.now(ZoneInfo("Asia/Riyadh"))
    return now.strftime("%Y-%m")


def resolve_tenant(phone_number_id: str | None) -> dict | None:
    """The tenant a message belongs to, by the WhatsApp number it arrived on."""
    return db.get_tenant_by_phone(phone_number_id) or db.get_default_tenant()


def check_quota(tenant: dict | None, *, is_voice: bool) -> Decision:
    """Decide whether to serve this message given the tenant's plan. Pure read —
    does not mutate usage. Unknown tenant or unlimited plan => allowed."""
    if not tenant:
        return Decision(True)

    # Safeguard: the platform's own clinic is never blocked by enforcement, so it
    # can't be accidentally locked out via the dashboard (status/plan/quota).
    if tenant.get("slug") == "default":
        return Decision(True)

    if tenant.get("status") in ("suspended", "expired"):
        return Decision(False, tenant["status"], MSG_UNAVAILABLE)

    ends = tenant.get("trial_ends_at")
    if tenant.get("is_trial") and ends and datetime.now(timezone.utc) > ends:
        return Decision(False, "trial_expired", MSG_UNAVAILABLE)

    if is_voice and not tenant.get("voice_enabled"):
        return Decision(False, "voice_not_allowed", MSG_VOICE_OFF)

    period = current_period(tenant.get("timezone") or "Asia/Riyadh")
    usage = db.get_usage(tenant["id"], period)
    if is_voice:
        quota = tenant.get("monthly_voice_quota")
        if quota is not None and usage["voice_count"] >= quota:
            return Decision(False, "voice_quota", MSG_QUOTA)
    else:
        quota = tenant.get("monthly_text_quota")
        if quota is not None and usage["text_count"] >= quota:
            return Decision(False, "text_quota", MSG_QUOTA)
    return Decision(True)


def record_usage(tenant: dict | None, *, is_voice: bool) -> None:
    """Increment this tenant's usage counter for the current period. Never raises."""
    if not tenant:
        return
    try:
        period = current_period(tenant.get("timezone") or "Asia/Riyadh")
        db.incr_usage(tenant["id"], period,
                      text=0 if is_voice else 1, voice=1 if is_voice else 0)
    except Exception:  # noqa: BLE001
        log.exception("Failed to record usage for tenant %s", tenant.get("id"))
