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
SAFE_REPLY_UR = (
    "معذرت — میں ابھی اس بکنگ کی تصدیق ہمارے سسٹم میں نہیں کر سکا۔ میں نے اسے عملے کے لیے "
    "نوٹ کر دیا ہے، وہ جلد ہی آپ کی اپائنٹمنٹ کی تصدیق کر دیں گے۔"
)
SAFE_REPLY_HI = (
    "क्षमा करें — मैं अभी हमारे सिस्टम में इस बुकिंग की पुष्टि नहीं कर सका। मैंने इसे हमारे स्टाफ "
    "के लिए नोट कर दिया है, वे जल्द ही आपकी अपॉइंटमेंट की पुष्टि कर देंगे।"
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
SAFE_AVAIL_DEFER_UR = (
    "مجھے دستیاب اوقات دوبارہ دیکھنے دیں تاکہ میں آپ کو درست اوقات بتا سکوں — ہماری ٹیم "
    "جلد ہی آپ کے ساتھ صحیح اوقات کی تصدیق کرے گی۔"
)
SAFE_AVAIL_DEFER_HI = (
    "मुझे उपलब्ध समय फिर से जांचने दें ताकि मैं आपको सही समय बता सकूं — हमारी टीम जल्द ही "
    "आपके साथ सही समय की पुष्टि करेगी।"
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
            ur=f"درست اوقات دینے کے لیے، دراصل دستیاب اوقات یہ ہیں: {shown}۔ آپ کے لیے کون سا مناسب ہے؟",
            hi=f"आपको सही समय देने के लिए, वास्तव में उपलब्ध समय ये हैं: {shown}। आपके लिए कौन सा ठीक रहेगा?",
        )
    return localize(user_text, SAFE_AVAIL_DEFER, SAFE_AVAIL_DEFER_AR, ur=SAFE_AVAIL_DEFER_UR,
                    hi=SAFE_AVAIL_DEFER_HI)


# --------------------------------------------------------------------------- language
# The reply MUST be in the patient's language: Arabic → Arabic, English → English, Urdu → Urdu,
# Hindi → Hindi. We work at the SCRIPT level because a correct reply still carries English
# tokens (doctor names, "mada", "SAR", digits) and an English reply may quote a foreign name —
# so the test is deliberately asymmetric and lenient to avoid false positives.
#
# Three scripts are counted: Perso-Arabic, Devanagari (Hindi) and Latin.
#  * Arabic and Urdu share the Perso-Arabic script. Urdu uses letters standard Arabic does not
#    (ٹ ڈ ڑ پ چ گ ک ہ ھ ں ے ی …); their presence marks Perso-Arabic text as Urdu.
#  * Hindi has its own script (Devanagari), so it is unambiguous in script.
#  * Romanised Hindi and Urdu (Latin: "appointment book ho gaya hai") overlap almost entirely
#    and cannot be told apart reliably — we treat shared romanised text as the Urdu bucket and
#    only flip to Hindi on a few distinctively-Hindi words.
_ARABIC_CHAR_RE = re.compile(
    "[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
_DEVANAGARI_CHAR_RE = re.compile(r"[ऀ-ॿ]")
_LATIN_CHAR_RE = re.compile(r"[A-Za-z]")
# Letters used by Urdu (and Persian) but not standard Arabic — a reliable Urdu-vs-Arabic tell.
_URDU_CHAR_RE = re.compile(
    "[ٹڈڑپچژگکیہھںۂۃےۓ]")
# High-signal romanised words shared by Hindi and Urdu (word-boundary matched). Kept specific to
# avoid firing on ordinary English; ambiguous short particles (ka/ki/ke/se/par/main) are omitted.
_ROMAN_INDIC_WORDS = (
    "hai", "hain", "kya", "kyun", "kaise", "kaisa", "kahan", "kab", "mujhe", "mera", "meri",
    "aap", "apka", "apko", "nahi", "nahin", "haan", "chahiye", "chahye", "gaya", "gayi", "gaye",
    "raha", "rahi", "rahe", "kitne", "kitna", "milega", "milegi", "shukriya", "theek", "acha",
    "achha", "krna", "karna", "karne",
)
_ROMAN_INDIC_RE = re.compile(r"\b(?:" + "|".join(_ROMAN_INDIC_WORDS) + r")\b", re.IGNORECASE)
# Distinctively-Hindi romanised words — present in Hindi but not idiomatic Urdu. Their presence
# tips ambiguous romanised text to Hindi; everything else in the shared set defaults to Urdu.
_ROMAN_HINDI_WORDS = (
    "namaste", "namaskar", "dhanyavaad", "dhanyawad", "kripya", "kripaya", "shubh", "samay",
)
_ROMAN_HINDI_RE = re.compile(r"\b(?:" + "|".join(_ROMAN_HINDI_WORDS) + r")\b", re.IGNORECASE)


def _script_counts(text: str) -> tuple[int, int, int]:
    """(perso-arabic, devanagari, latin) letter counts."""
    t = text or ""
    return (len(_ARABIC_CHAR_RE.findall(t)),
            len(_DEVANAGARI_CHAR_RE.findall(t)),
            len(_LATIN_CHAR_RE.findall(t)))


def _has_urdu_script(text: str) -> bool:
    return bool(_URDU_CHAR_RE.search(text or ""))


def _has_devanagari(text: str) -> bool:
    return bool(_DEVANAGARI_CHAR_RE.search(text or ""))


def _roman_lang(text: str) -> str:
    """Classify Latin-script text: 'hi' (distinctively Hindi), 'ur' (shared romanised Indic),
    or 'en'. Shared romanised text defaults to Urdu since Hindi and Urdu are indistinguishable."""
    if _ROMAN_HINDI_RE.search(text or ""):
        return "hi"
    if _ROMAN_INDIC_RE.search(text or ""):
        return "ur"
    return "en"


def detect_language(text: str) -> str | None:
    """'ar', 'ur', 'hi', 'en', or None when there aren't enough letters to tell."""
    pa, dev, la = _script_counts(text)
    if not pa and not dev and not la:
        return None
    if dev and dev >= pa and dev >= la:           # Devanagari dominates → Hindi
        return "hi"
    if pa and pa >= la:                           # Perso-Arabic dominates
        return "ur" if _has_urdu_script(text) else "ar"
    return _roman_lang(text)                       # Latin dominates


def localize(user_text: str, en: str, ar: str, ur: str | None = None, hi: str | None = None) -> str:
    """Localise a canned reply to the patient's language. Defaults to English unless the patient
    clearly wrote Arabic, Urdu or Hindi (Urdu/Hindi fall back to English if not provided)."""
    lang = detect_language(user_text)
    if lang == "ar":
        return ar
    if lang == "ur":
        return ur if ur is not None else en
    if lang == "hi":
        return hi if hi is not None else en
    return en


def language_mismatch(user_text: str, reply: str) -> bool:
    """True when the reply clearly answers in the wrong language for the patient.

    Asymmetric and lenient to avoid false positives — a correct reply that merely quotes
    foreign names/codes is never flagged:
      * Arabic/Urdu patient → flag if the reply has NO Perso-Arabic script at all, or is in
        the other Perso-Arabic language (Arabic reply to an Urdu patient, or vice versa).
      * Hindi-script patient → flag if the reply has NO Devanagari at all.
      * English patient → flag if the reply is DOMINATED by a non-Latin script.
      * Romanised Hindi/Urdu patient → flag only if the reply switched to a non-Latin script;
        a Latin reply is left alone (romanised Indic can't be told apart from English)."""
    pa_r, dev_r, la_r = _script_counts(reply)
    nonlatin_r = pa_r + dev_r
    if not pa_r and not dev_r and not la_r:
        return False                              # reply has no letters to judge
    want = detect_language(user_text)
    if want == "ar":
        if pa_r == 0:
            return True                           # asked in Arabic, answered with no Arabic
        return _has_urdu_script(reply)            # answered in Urdu instead of Arabic
    if want == "ur":
        if _has_urdu_script(user_text):           # patient wrote Urdu SCRIPT
            if pa_r == 0:
                return True                       # answered with no Perso-Arabic at all
            return not _has_urdu_script(reply)    # answered in Arabic, not Urdu
        # patient wrote romanised Urdu (Latin) — only flag a switch to a non-Latin script
        return nonlatin_r > 0 and nonlatin_r >= la_r
    if want == "hi":
        if _has_devanagari(user_text):            # patient wrote Hindi SCRIPT
            return dev_r == 0                     # answered with no Devanagari
        # patient wrote romanised Hindi (Latin) — only flag a switch to a non-Latin script
        return nonlatin_r > 0 and nonlatin_r >= la_r
    if want == "en":
        return nonlatin_r > 0 and nonlatin_r >= la_r  # asked in English, answered in script
    return False                                  # patient language unknown → don't police


def verify(ctx, user_text: str = "") -> None:
    """Mutate ctx in place: block an unbacked booking confirmation, else block an invented
    availability offer. Escalates to staff in either case."""
    if should_block(ctx):
        log.error("BLOCKED unbacked booking confirmation (tenant %s, user %s): %r",
                  ctx.tenant_id, ctx.wa_user, (ctx.reply or "")[:200])
        ctx.reply = localize(user_text, SAFE_REPLY, SAFE_REPLY_AR, ur=SAFE_REPLY_UR,
                             hi=SAFE_REPLY_HI)
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
