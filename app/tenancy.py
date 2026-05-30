"""Tenant resolution + usage metering.

Phase 1: identify the tenant for an inbound message (by WhatsApp phone_number_id,
falling back to the default tenant) and count text/voice usage per calendar month.
Quota *enforcement* is layered on in a later phase; counting is always safe.
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app import db

log = logging.getLogger(__name__)


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
