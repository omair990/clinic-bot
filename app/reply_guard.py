"""Strict patient-facing truthfulness guards.

The model writes replies in free prose, so it can *state* things that aren't true:
  1. claim an appointment is booked/confirmed when the tool errored or wasn't called, or
  2. offer appointment times that the availability tool never returned.

These guards refuse to let either reach the patient:
  * Booking guard — if the reply claims a booking but there is no database-backed
    appointment (none booked/rescheduled this turn, and none confirmed-and-upcoming in the
    DB), swap in a safe message and escalate to staff.
  * Availability guard — if the reply offers a clock time that the availability tool did NOT
    return this turn (and the patient didn't propose it), the bot is inventing availability;
    correct it to the real slots (or defer) and escalate. Only active once availability was
    actually checked, so it never fires on general "we're open 9–11" answers.

The decision functions are pure and unit-tested; `verify` applies them to the context.
"""
import logging
import re

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
SAFE_REPLY_AR = (
    "عذرًا، لم أتمكن من تأكيد هذا الحجز في نظامنا حتى الآن. لقد أبلغت فريقنا وسيؤكدون موعدك "
    "معك قريبًا."
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


# --------------------------------------------------------------------------- availability
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
# "5 PM", "5:30pm", "17:00", "9 a.m.", "٥ مساءً"
_TIME_RE = re.compile(
    r"(?<!\d)(\d{1,2})(?::(\d{2}))?\s*"
    r"(a\.?m\.?|p\.?m\.?|صباح\w*|مساء\w*)?",
    re.IGNORECASE,
)
_PM_WORDS = ("pm", "p.m", "p.m.", "مساء")
_AM_WORDS = ("am", "a.m", "a.m.", "صباح")

SAFE_AVAIL_DEFER = (
    "Let me re-check the available times so I give you accurate slots — our team will "
    "confirm the exact times with you shortly."
)
SAFE_AVAIL_DEFER_AR = (
    "دعني أتحقق من الأوقات المتاحة مرة أخرى لأعطيك مواعيد دقيقة — سيؤكد فريقنا الأوقات "
    "معك قريبًا."
)


def _hhmm(h: int, m: int) -> str:
    return f"{h % 24:02d}:{m:02d}"


def _fmt_12h(hhmm: str) -> str:
    h, m = (int(x) for x in hhmm.split(":"))
    ap = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {ap}"


def time_mentions(text: str) -> list[set]:
    """Every clock time mentioned, each as a set of plausible 'HH:MM' values. A bare hour
    with no am/pm yields both interpretations (lenient — avoids false positives); an explicit
    meridiem or a 24h value yields one. Bare integers without ':' or am/pm are ignored, so
    prices/durations/dates don't register."""
    text = (text or "").translate(_AR_DIGITS)
    out: list[set] = []
    for m in _TIME_RE.finditer(text):
        hour = int(m.group(1))
        has_min = m.group(2) is not None
        minute = int(m.group(2)) if has_min else 0
        mer = (m.group(3) or "").lower()
        if hour > 23 or minute > 59:
            continue
        # require a real time token: a ':MM' or an explicit meridiem
        if not has_min and not mer:
            continue
        if any(mer.startswith(w) for w in _PM_WORDS):
            out.append({_hhmm(hour if hour == 12 else hour + 12, minute)})
        elif any(mer.startswith(w) for w in _AM_WORDS):
            out.append({_hhmm(0 if hour == 12 else hour, minute)})
        elif hour >= 13:
            out.append({_hhmm(hour, minute)})              # unambiguous 24h
        else:
            out.append({_hhmm(hour, minute), _hhmm(hour + 12, minute)})  # am or pm
    return out


def _allowed_times(ctx, user_text: str) -> set:
    """Times the reply may mention: real slots surfaced this turn + times the patient
    themselves proposed (so 'you asked for 5 PM, but it's taken' isn't flagged)."""
    allowed = set(getattr(ctx, "offered_times", set()) or set())
    for cand in time_mentions(user_text):
        allowed |= cand
    return allowed


def unverified_offer_times(ctx, user_text: str) -> list[set]:
    allowed = _allowed_times(ctx, user_text)
    return [cand for cand in time_mentions(ctx.reply) if not (cand & allowed)]


def should_block_availability(ctx, user_text: str = "") -> bool:
    """True if the reply offers a time the availability tool didn't return this turn."""
    if not getattr(ctx, "availability_checked", False):
        return False                       # availability never checked → don't police times
    return bool(unverified_offer_times(ctx, user_text))


def _availability_reply(ctx, user_text: str = "") -> str:
    real = sorted(getattr(ctx, "offered_times", set()) or set())
    if real:
        shown = ", ".join(_fmt_12h(t) for t in real[:12])
        return localize(
            user_text,
            "To make sure I give you the right times, the actually available slots are: "
            f"{shown}. Which one works for you?",
            f"للتأكد من إعطائك الأوقات الصحيحة، المواعيد المتاحة فعليًا هي: {shown}. أيها يناسبك؟",
        )
    return localize(user_text, SAFE_AVAIL_DEFER, SAFE_AVAIL_DEFER_AR)


# --------------------------------------------------------------------------- language
# The reply MUST be in the patient's language: Arabic in → Arabic out, English in → English
# out. We compare scripts, not the full language, because a correct Arabic reply still carries
# English tokens (doctor names, "mada", "SAR", digits) and an English reply may quote an Arabic
# name — so the test is deliberately asymmetric and lenient to avoid false positives.
_ARABIC_CHAR_RE = re.compile(
    "[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
_LATIN_CHAR_RE = re.compile(r"[A-Za-z]")


def _letter_counts(text: str) -> tuple[int, int]:
    t = text or ""
    return len(_ARABIC_CHAR_RE.findall(t)), len(_LATIN_CHAR_RE.findall(t))


def detect_language(text: str) -> str | None:
    """'ar', 'en', or None when there aren't enough letters to tell (digits/emoji only)."""
    ar, la = _letter_counts(text)
    if not ar and not la:
        return None
    if ar and not la:
        return "ar"
    if la and not ar:
        return "en"
    return "ar" if ar >= la else "en"   # mixed script → dominant one


def localize(user_text: str, en: str, ar: str) -> str:
    """Localise a canned reply to the patient's language (English unless clearly Arabic)."""
    return ar if detect_language(user_text) == "ar" else en


def language_mismatch(user_text: str, reply: str) -> bool:
    """True when the reply clearly answers in the wrong language for the patient.

    Asymmetric on purpose: an Arabic patient getting a reply with NO Arabic at all is a
    mismatch; an English patient getting a reply DOMINATED by Arabic script is a mismatch.
    A correct Arabic reply that merely quotes English names/codes is never flagged."""
    ar_r, la_r = _letter_counts(reply)
    if not ar_r and not la_r:
        return False                       # reply has no letters to judge
    want = detect_language(user_text)
    if want == "ar":
        return ar_r == 0                   # asked in Arabic, answered with no Arabic
    if want == "en":
        return ar_r > 0 and ar_r >= la_r   # asked in English, answered mostly in Arabic
    return False                           # patient language unknown → don't police


def verify(ctx, user_text: str = "") -> None:
    """Mutate ctx in place: block an unbacked booking confirmation, else block an invented
    availability offer. Escalates to staff in either case."""
    if should_block(ctx):
        log.error("BLOCKED unbacked booking confirmation (tenant %s, user %s): %r",
                  ctx.tenant_id, ctx.wa_user, (ctx.reply or "")[:200])
        ctx.reply = localize(user_text, SAFE_REPLY, SAFE_REPLY_AR)
        ctx.needs_human = True
        ctx.guard_tripped = True
        return
    if should_block_availability(ctx, user_text):
        bad = unverified_offer_times(ctx, user_text)
        log.error("BLOCKED invented availability (tenant %s, user %s): offered %s not in %s | %r",
                  ctx.tenant_id, ctx.wa_user, bad, sorted(getattr(ctx, "offered_times", set())),
                  (ctx.reply or "")[:200])
        ctx.reply = _availability_reply(ctx, user_text)
        ctx.needs_human = True
        ctx.guard_tripped = True
