"""Strict booking-confirmation guard.

The model writes the patient-facing reply in free prose, so it can *say* an appointment is
booked/confirmed even when the booking tool returned an error or was never called. This
guard refuses to let an unbacked confirmation reach the patient: if the reply claims a
booking but there is **no database-backed appointment** for this patient, it swaps in a safe
message and escalates to staff.

A claim is considered backed if either:
  * an appointment was booked/rescheduled *this turn* (`ctx.booked_ids` / `ctx.changed_ids`,
    already verified against the DB by the booking tools), or
  * the patient already has a confirmed, not-yet-ended appointment in the DB (so confirming
    an existing booking on a later turn is truthful).

`should_block` is pure and unit-tested; `verify` applies the decision to the context.
"""
import logging

from app import db

log = logging.getLogger(__name__)

# Confirmation phrases (not bare "book", which appears in questions like "to book…").
# English + Arabic + Urdu/Hindi (incl. roman) — the assistant replies in the patient's language.
_CONFIRM_CUES = (
    "is booked", "are booked", "you're booked", "youre booked", "have booked", "have been booked",
    "is confirmed", "appointment is", "appointment has been", "successfully booked",
    "successfully scheduled", "reserved for you", "see you on", "see you at",
    "booking is confirmed", "all set for",
    # Arabic
    "تم الحجز", "تم حجز", "تم تأكيد", "موعدك", "محجوز", "حجزت لك", "تم تثبيت",
    # Urdu / Hindi (incl. roman transliteration)
    "اپوائنٹمنٹ بک", "بک ہو گیا", "بک ہو گئی", "کنفرم ہو", "ہو گیا ہے",
    "book ho gaya", "book ho gayi", "confirm ho gaya", "ho gaya hai", "बुक हो ग",
)

SAFE_REPLY = (
    "I'm sorry — I couldn't confirm that booking in our system just yet. I've flagged this for "
    "our staff and they'll confirm your appointment with you shortly."
)


def claims_booking(text: str) -> bool:
    """Whether the reply asserts a completed booking/confirmation."""
    t = (text or "").lower()
    return any(cue in t for cue in _CONFIRM_CUES)


def _has_backed_appointment(ctx) -> bool:
    # Booked/rescheduled this turn (the booking tools already re-read these from the DB).
    if getattr(ctx, "booked_ids", None) or getattr(ctx, "changed_ids", None):
        return True
    # Or an existing confirmed, not-yet-ended appointment — a truthful confirmation.
    if not ctx.tenant_id:
        return False
    try:
        return db.has_confirmed_upcoming(ctx.tenant_id, ctx.wa_user)
    except Exception:  # noqa: BLE001 — a lookup failure must not let a false claim through
        log.warning("reply_guard DB check failed for %s; treating as unbacked", ctx.wa_user)
        return False


def should_block(ctx) -> bool:
    """True if the reply claims a booking but nothing in the DB backs it."""
    return claims_booking(ctx.reply) and not _has_backed_appointment(ctx)


def verify(ctx) -> None:
    """Mutate ctx in place: block an unbacked booking confirmation and escalate."""
    if not should_block(ctx):
        return
    log.error("BLOCKED unbacked booking confirmation (tenant %s, user %s): %r",
              ctx.tenant_id, ctx.wa_user, (ctx.reply or "")[:200])
    ctx.reply = SAFE_REPLY
    ctx.needs_human = True
    ctx.guard_tripped = True
