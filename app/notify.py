"""Notification routing — who gets a WhatsApp ping for what.

Two audiences, kept strictly separate:

* **Clinic-facing** (patient escalations, new bookings, insights digests) → that clinic's
  OWN recipients, sent from the clinic's WhatsApp number. Recipients live in
  ``tenant.clinic_data.notifications.recipients`` — a list of
  ``{label, number, escalation: bool, digest: bool}`` so a clinic can route to several
  people (e.g. front desk + owner) and pick who gets escalations vs. the daily digest.
  The legacy single ``clinic_data.owner_wa_number`` is still honored (Owner, both kinds).

* **Platform-facing** (technical incidents: LLM down, agent crash, send failures) → the
  super-admin number(s) in ``ADMIN_WA_NUMBER`` (comma-separated for several), sent from the
  platform's default WhatsApp number. This is the ONLY thing the super-admin is paged for.

Every send is best-effort: a failed ping is logged + recorded as an incident, never raised,
so notifications can't break the request they report on.
"""
import asyncio
import logging

from app import incidents, wa_client
from app.config import ADMIN_WA_NUMBER

log = logging.getLogger(__name__)


def _clean(seq) -> list[str]:
    """De-duped, trimmed, order-preserving list of non-empty numbers."""
    seen: set[str] = set()
    out: list[str] = []
    for n in seq:
        n = str(n or "").strip()
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def recipients(tenant: dict | None) -> list[dict]:
    """Normalized recipient entries for a clinic (label/number/escalation/digest)."""
    cd = (tenant or {}).get("clinic_data") or {}
    raw = (cd.get("notifications") or {}).get("recipients")
    out: list[dict] = []
    if isinstance(raw, list):
        for r in raw:
            if isinstance(r, dict) and str(r.get("number") or "").strip():
                out.append({
                    "label": str(r.get("label") or "").strip() or "Recipient",
                    "number": str(r["number"]).strip(),
                    "escalation": bool(r.get("escalation", True)),
                    "digest": bool(r.get("digest", False)),
                })
    if out:
        return out
    # Legacy: a single owner number gets both escalations and the digest.
    legacy = str(cd.get("owner_wa_number") or "").strip()
    if legacy:
        return [{"label": "Owner", "number": legacy, "escalation": True, "digest": True}]
    return []


def clinic_numbers(tenant: dict | None, kind: str) -> list[str]:
    """Clinic recipient numbers opted into ``kind`` ('escalation' | 'digest')."""
    return _clean(r["number"] for r in recipients(tenant) if r.get(kind))


def tech_numbers() -> list[str]:
    """Platform-admin number(s) for technical alerts (ADMIN_WA_NUMBER, comma/semicolon-split)."""
    from app import settings
    raw = settings.get("ADMIN_WA_NUMBER", ADMIN_WA_NUMBER) or ""
    return _clean(raw.replace(";", ",").split(","))


async def _send_one(number: str, text: str, creds: dict | None, what: str) -> bool:
    try:
        if creds and creds.get("phone_number_id"):
            await wa_client.send_text(number, text, **creds)
        else:
            await wa_client.send_text(number, text)
        return True
    except Exception as e:  # noqa: BLE001 — a notify failure must never break the caller
        log.warning("notify %s to %s failed: %s", what, number, str(e)[:160])
        await asyncio.to_thread(incidents.record, "whatsapp", f"Could not notify {what} number",
                                level="warning", detail=str(e)[:300])
        return False


async def send_many(numbers, text: str, *, creds: dict | None = None, what: str = "recipient") -> int:
    """Send ``text`` to each number; returns how many succeeded."""
    sent = 0
    for n in _clean(numbers):
        if await _send_one(n, text, creds, what):
            sent += 1
    return sent


async def notify_clinic(tenant: dict | None, text: str, *, kind: str = "escalation") -> int:
    """Ping a clinic's own recipients (from the clinic's WhatsApp number)."""
    creds = {"phone_number_id": (tenant or {}).get("wa_phone_number_id"),
             "access_token": (tenant or {}).get("wa_access_token")}
    return await send_many(clinic_numbers(tenant, kind), text, creds=creds, what="clinic staff")


async def notify_tech(text: str) -> int:
    """Ping the platform admin number(s) for a technical issue (default WhatsApp number)."""
    return await send_many(tech_numbers(), text, what="platform admin")
