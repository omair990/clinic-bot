"""Patient-facing notifications for staff actions taken in the dashboard.

When staff cancel or complete an appointment from the admin UI, the patient should hear
about it on WhatsApp — not just see a silent status change. Kept separate from the agent
so it has no LLM dependency: the copy is deterministic and the send is logged to the
conversation + live feed like any other outbound message.

NOTE: same WhatsApp 24-hour-window caveat as the no-show messages — outside the window a
business-initiated message needs an approved template; this sends free-form text.
"""
import asyncio
import logging

from app import db
from app.config import TZ
from app.events import publish
from app.wa_client import send_text

log = logging.getLogger(__name__)


def _when(start_at) -> str:
    return start_at.astimezone(TZ).strftime("%A %d %B, %I:%M %p")


def _clinic_name(tenant: dict) -> str:
    return (((tenant.get("clinic_data") or {}).get("clinic") or {}).get("name")
            or tenant.get("name") or "our clinic")


def appointment_status_message(status: str, service: str | None, doctor: str | None,
                               when: str, clinic_name: str) -> str | None:
    """Patient message for a dashboard status change, or None if the status isn't one
    we notify on (only cancel/complete)."""
    subject = f"{service} with {doctor}" if service and doctor else "your appointment"
    if status == "cancelled":
        return (f"Your appointment ({subject}) on {when} at {clinic_name} has been "
                "cancelled. Reply here anytime to rebook — we're happy to help.")
    if status == "completed":
        return (f"Thank you for visiting {clinic_name}! We hope {subject} went well. "
                "Reply here if you'd like a follow-up or anything else. 😊")
    return None


async def notify_appointment_status(appt: dict, status: str, tenant: dict) -> bool:
    """Send the patient a WhatsApp message about a cancel/complete and mirror it to the
    conversation log + live feed. Returns True if a message was sent."""
    msg = appointment_status_message(
        status, appt.get("service"), appt.get("doctor"), _when(appt["start_at"]),
        _clinic_name(tenant))
    if not msg:
        return False
    creds = {"phone_number_id": tenant.get("wa_phone_number_id"),
             "access_token": tenant.get("wa_access_token")}
    await send_text(appt["wa_user"], msg, **creds)
    await asyncio.to_thread(db.log_message, tenant["id"], appt["wa_user"], "out", msg,
                            "appointment", False)
    publish("message", {"wa_user": appt["wa_user"], "direction": "out", "text": msg,
                        "intent": "appointment", "tenant_id": tenant["id"]})
    log.info("status-change notice (%s) sent to %s", status, appt["wa_user"])
    return True
