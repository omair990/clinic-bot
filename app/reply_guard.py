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
import threading
import unicodedata
from functools import lru_cache

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
# The reply MUST be in the patient's language, for ANY language. Two layers:
#
#  1. SCRIPT layer (fast, dependency-free, very lenient) handles the languages we see most and
#     the cases a statistical detector gets wrong on short text:
#       * Arabic vs Urdu — both Perso-Arabic; Urdu uses letters Arabic does not (ٹ ڈ ڑ پ چ گ ک
#         ہ ھ ں ے ی …), so their presence marks the text as Urdu.
#       * Hindi — its own script (Devanagari), unambiguous.
#       * Romanised Hindi/Urdu ("appointment book ho gaya hai") — Latin; spotted by a small word
#         list (the two overlap almost entirely, so shared text is the Urdu bucket).
#     For these we compare by SCRIPT and stay lenient: a correct reply still carries English
#     tokens (doctor names, "mada", "SAR", digits), so an Arabic/Urdu/Hindi reply is only
#     flagged when it has NONE of the expected script.
#
#  2. LANGUAGE-ID layer (py3langid) handles every OTHER language:
#       * other scripts (Bengali, Tamil, Thai, Cyrillic, CJK, …) — compared by Unicode script,
#         which is robust even on short text;
#       * Latin-script languages (Spanish, French, Tagalog, …) — distinguished from English by
#         a curated, length-gated, English-protective classifier. Statistical LID is unreliable
#         on short text, so we default to English (the clinic's lingua franca) unless a long
#         enough message is confidently another language — precision over recall, so we never
#         wrongly demand a non-English reply from an English speaker.
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
# Tagalog (Filipino) is Latin-script and short messages confuse the statistical classifier
# (e.g. "Gusto ko po…" → Italian). A high-precision word override fixes that. STRONG words are
# Tagalog-specific (one is enough); COMMON particles need two to fire. Ambiguous tokens are
# deliberately omitted: "sa" (French "his/her"), "gusto" (Spanish/Italian), "lang" (German).
_TAGALOG_STRONG_WORDS = (
    "magkano", "magkanu", "pwede", "puwede", "salamat", "kailangan", "ngipin", "opo", "mga",
    "kayo", "namin", "ninyo", "naman", "meron", "bukas", "magpapa", "magpa",
)
_TAGALOG_COMMON_WORDS = (
    "po", "ang", "ng", "ko", "ako", "niyo", "yung", "saan", "dito", "doon", "kasi", "ito",
)
_TAGALOG_STRONG_RE = re.compile(r"\b(?:" + "|".join(_TAGALOG_STRONG_WORDS) + r")\b", re.IGNORECASE)
_TAGALOG_COMMON_RE = re.compile(r"\b(?:" + "|".join(_TAGALOG_COMMON_WORDS) + r")\b", re.IGNORECASE)


def _is_tagalog(text: str) -> bool:
    """High-precision Tagalog check: one distinctive word, or two common particles."""
    t = text or ""
    return bool(_TAGALOG_STRONG_RE.search(t)) or len(_TAGALOG_COMMON_RE.findall(t)) >= 2

# --- py3langid (statistical language ID) for every other language -------------
# Restricted to a curated, extensible set of languages a Riyadh clinic realistically sees —
# this both improves accuracy (fewer rare-language false attractors) and bounds the output.
_CURATED_LANGS = (
    "en", "ar", "ur", "hi", "fa", "ps", "bn", "ta", "te", "ml", "kn", "gu", "mr", "ne", "pa",
    "si", "es", "fr", "pt", "it", "de", "nl", "ru", "uk", "tr", "id", "ms", "tl", "sw", "am",
    "zh", "ja", "ko", "th", "vi", "he", "el",
)
_MIN_LATIN_CHARS = 25        # below this, Latin-script text is too short to trust → assume English
_LATIN_CONF = 0.90           # confidence required to call Latin text a non-English language
_OTHER_CONF = 0.50           # confidence required to name a non-Latin (other-script) language

_lid_lock = threading.Lock()
_lid_identifier = None


def _identifier():
    """Lazily build the langid identifier (loads a pickled model once)."""
    global _lid_identifier
    if _lid_identifier is None:
        from py3langid.langid import MODEL_FILE, LanguageIdentifier
        ident = LanguageIdentifier.from_pickled_model(MODEL_FILE, norm_probs=True)
        supported = set(ident.nb_classes)
        ident.set_languages([l for l in _CURATED_LANGS if l in supported])
        _lid_identifier = ident
    return _lid_identifier


@lru_cache(maxsize=2048)
def _classify(text: str) -> tuple[str | None, float]:
    """(iso code, confidence in 0..1), or (None, 0.0) on any failure. Thread-safe + cached."""
    t = (text or "").strip()
    if not t:
        return None, 0.0
    try:
        with _lid_lock:
            lang, conf = _identifier().classify(t)
        return lang, float(conf)
    except Exception:  # noqa: BLE001 — language ID must never break a turn
        log.warning("langid classify failed", exc_info=True)
        return None, 0.0


@lru_cache(maxsize=4096)
def _char_script(ch: str) -> str | None:
    """Unicode script family of a character, e.g. 'LATIN', 'ARABIC', 'DEVANAGARI', 'BENGALI',
    'CJK', 'HANGUL', 'THAI', 'CYRILLIC' … (the first word of its Unicode name)."""
    try:
        return unicodedata.name(ch).split(" ")[0]
    except ValueError:
        return None


def _script_counts(text: str) -> tuple[int, int, int, int]:
    """(perso-arabic, devanagari, latin, other) letter counts. 'other' is any alphabetic
    character in a further script (Bengali, Tamil, Thai, CJK, Cyrillic, …)."""
    pa = dev = la = oth = 0
    for ch in text or "":
        if not ch.isalpha():
            continue
        s = _char_script(ch)
        if s == "ARABIC":
            pa += 1
        elif s == "DEVANAGARI":
            dev += 1
        elif s == "LATIN":
            la += 1
        else:
            oth += 1
    return pa, dev, la, oth


def _dominant_script(text: str) -> str | None:
    """The most common Unicode script family among the text's letters, or None if it has none."""
    counts: dict[str, int] = {}
    for ch in text or "":
        if not ch.isalpha():
            continue
        s = _char_script(ch)
        if s:
            counts[s] = counts.get(s, 0) + 1
    return max(counts, key=counts.get) if counts else None


def _has_urdu_script(text: str) -> bool:
    return bool(_URDU_CHAR_RE.search(text or ""))


def _has_devanagari(text: str) -> bool:
    return bool(_DEVANAGARI_CHAR_RE.search(text or ""))


def _roman_lang(text: str) -> str:
    """Classify Latin-script text as romanised Indic: 'hi' (distinctively Hindi), 'ur' (shared
    romanised Indic), or 'en'. Shared text defaults to Urdu (Hindi/Urdu are indistinguishable)."""
    if _ROMAN_HINDI_RE.search(text or ""):
        return "hi"
    if _ROMAN_INDIC_RE.search(text or ""):
        return "ur"
    return "en"


def _latin_only(text: str) -> str:
    """Drop non-Latin letters (e.g. an Arabic doctor name) so they don't skew Latin LID."""
    return "".join(ch if (not ch.isalpha() or _char_script(ch) == "LATIN") else " "
                   for ch in text or "")


def _latin_lang(text: str) -> str:
    """ISO code for Latin-script text — 'en' unless a high-precision override (Tagalog) fires,
    or it is long enough AND confidently another Latin-script language. Biased to English to
    avoid false positives on short text."""
    if _is_tagalog(text):
        return "tl"                          # high-precision override (langid confuses short tl)
    lo = _latin_only(text).strip()
    if len(lo) < _MIN_LATIN_CHARS:
        return "en"
    lang, conf = _classify(lo)
    if lang is None or lang == "en" or conf < _LATIN_CONF:
        return "en"
    return lang


def detect_language(text: str) -> str | None:
    """Best-effort language of the text as an ISO code ('ar', 'ur', 'hi', 'en', 'es', 'bn', …),
    or None when there aren't enough letters to tell (digits/emoji only). Used to localise canned
    replies and to name the language in the regeneration nudge."""
    pa, dev, la, oth = _script_counts(text)
    if not (pa or dev or la or oth):
        return None
    m = max(pa, dev, la, oth)
    if pa == m:
        return "ur" if _has_urdu_script(text) else "ar"
    if dev == m:
        return "hi"
    if oth == m:
        lang, conf = _classify(text)
        return lang if (lang and conf >= _OTHER_CONF) else None
    roman = _roman_lang(text)               # Latin dominates
    return roman if roman != "en" else _latin_lang(text)


def localize(user_text: str, en: str, ar: str, ur: str | None = None, hi: str | None = None) -> str:
    """Localise a canned reply to the patient's language. Only English/Arabic/Urdu/Hindi have
    canned translations; every other language falls back to English."""
    lang = detect_language(user_text)
    if lang == "ar":
        return ar
    if lang == "ur":
        return ur if ur is not None else en
    if lang == "hi":
        return hi if hi is not None else en
    return en


def language_mismatch(user_text: str, reply: str) -> bool:
    """True when the reply clearly answers in the wrong language for the patient — for any
    language. Asymmetric and lenient so a correct reply quoting foreign names/codes is never
    flagged. Routes by the patient's dominant script:
      * Arabic/Urdu patient → flag if the reply has NO Perso-Arabic at all, or is the other
        Perso-Arabic language (Arabic reply to an Urdu patient, or vice versa).
      * Hindi-script patient → flag if the reply has NO Devanagari.
      * Other-script patient (Bengali, Thai, CJK, …) → flag if the reply's dominant script differs.
      * Romanised Hindi/Urdu patient → flag only a switch to a non-Latin script (romanised Indic
        can't be told from English, so Latin replies are left alone).
      * Latin-script patient (English/Spanish/French/…) → flag a non-Latin reply, else flag when
        the reply's Latin language differs from the patient's."""
    pa_u, dev_u, la_u, oth_u = _script_counts(user_text)
    if not (pa_u or dev_u or la_u or oth_u):
        return False                              # patient text has no letters → can't tell
    pa_r, dev_r, la_r, oth_r = _script_counts(reply)
    if not (pa_r or dev_r or la_r or oth_r):
        return False                              # reply has no letters to judge
    nonlatin_r = pa_r + dev_r + oth_r

    if pa_u >= dev_u and pa_u >= la_u and pa_u >= oth_u and pa_u:   # Perso-Arabic patient
        if _has_urdu_script(user_text):           # Urdu SCRIPT
            if pa_r == 0:
                return True                       # answered with no Perso-Arabic at all
            return not _has_urdu_script(reply)    # answered in Arabic, not Urdu
        if pa_r == 0:
            return True                           # Arabic asked, answered with no Arabic
        return _has_urdu_script(reply)            # answered in Urdu instead of Arabic
    if dev_u >= la_u and dev_u >= oth_u and dev_u:                  # Devanagari (Hindi) patient
        return dev_r == 0
    if oth_u > la_u and oth_u:                                     # other-script patient
        return _dominant_script(reply) != _dominant_script(user_text)
    # Latin-script patient — romanised Indic, or a genuine Latin-script language.
    roman = _roman_lang(user_text)
    if roman in ("ur", "hi"):                     # romanised Urdu/Hindi
        return nonlatin_r > 0 and nonlatin_r >= la_r
    if nonlatin_r > 0 and nonlatin_r >= la_r:
        return True                               # English/etc. asked, answered in another script
    return _latin_lang(reply) != _latin_lang(user_text)


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
