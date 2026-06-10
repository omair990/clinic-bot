"""Strict booking-confirmation guard: a 'booked' reply must be backed by a DB appointment."""
from app import reply_guard
from app.tools import AgentContext


def _ctx(reply, *, booked=None, changed=None, tenant_id=1):
    c = AgentContext(wa_user="966500000000", tenant_id=tenant_id)
    c.reply = reply
    c.booked_ids = booked or []
    c.changed_ids = changed or []
    return c


# --- claim detection ----------------------------------------------------------
def test_claims_booking_detects_confirmations():
    for t in ["Your appointment is booked for 5 PM.",
              "All set for tomorrow at 10!",
              "تم الحجز مع الدكتور خالد",
              "Aap ka appointment book ho gaya hai"]:
        assert reply_guard.claims_booking(t), t


def test_claims_booking_ignores_non_confirmations():
    for t in ["To book an appointment, what day works for you?",
              "We are open from 9 to 5.",
              "Dr. Khalid is available on Sunday and Monday."]:
        assert not reply_guard.claims_booking(t), t


def test_claims_booking_ignores_generic_completion_and_possessive_phrases():
    # Regression: generic "is done" / "your appointment" phrases must NOT read as a booking
    # confirmation — they fire on ordinary replies (e.g. answering "can you speak Urdu?").
    for t in ["جی ہاں! بالکل۔ بتائیں آپ کا کام کیسے ہو گیا ہے؟",   # Urdu "how was it done?"
              "Aapka sawal samajh ho gaya hai, bataiye.",            # roman "your question is understood"
              "Of course, your appointment is something I can help with. What day?",
              "What time would you like your appointment? موعدك سيكون مناسبًا"]:
        assert not reply_guard.claims_booking(t), t


def test_claims_booking_ignores_offer_phrasing():
    # Regression (seen live): an OFFER to book ("do you want to book an appointment?") must NOT
    # read as a completed booking. Mirrors how bare English "book an appointment" is excluded.
    for t in ["کیا آپ کو اپوائنٹمنٹ بک کرنی ہے یا کوئی اور معلومات چاہیے؟",  # "want to book one?"
              "Would you like to book an appointment?",
              "آپ اپوائنٹمنٹ بک کرنا چاہتے ہیں؟"]:
        assert not reply_guard.claims_booking(t), t


def test_claims_booking_still_detects_urdu_completed_booking():
    for t in ["آپ کی اپوائنٹمنٹ بک ہو گئی ہے۔",      # "your appointment got booked"
              "اپوائنٹمنٹ بک ہو گیا"]:
        assert reply_guard.claims_booking(t), t


# --- blocking decision (no DB needed: backed this turn) -----------------------
def test_backed_by_this_turn_booking_is_allowed():
    c = _ctx("Your appointment is booked for 5 PM.", booked=[42])
    assert reply_guard.should_block(c) is False


def test_backed_by_reschedule_is_allowed():
    c = _ctx("Your appointment is confirmed for the new time.", changed=[7])
    assert reply_guard.should_block(c) is False


def test_unbacked_confirmation_is_blocked(monkeypatch):
    monkeypatch.setattr(reply_guard.db, "has_confirmed_upcoming", lambda t, u: False)
    c = _ctx("Great news — your appointment is booked for 5 PM!")
    assert reply_guard.should_block(c) is True


def test_existing_db_appointment_backs_a_confirmation(monkeypatch):
    # No booking this turn, but the patient already has a confirmed appointment.
    monkeypatch.setattr(reply_guard.db, "has_confirmed_upcoming", lambda t, u: True)
    c = _ctx("Yes, your appointment is confirmed for Sunday.")
    assert reply_guard.should_block(c) is False


def test_non_booking_reply_never_blocked(monkeypatch):
    monkeypatch.setattr(reply_guard.db, "has_confirmed_upcoming", lambda t, u: False)
    c = _ctx("We're open 9 to 5. How can I help?")
    assert reply_guard.should_block(c) is False


def test_db_failure_treated_as_unbacked(monkeypatch):
    def boom(t, u):
        raise RuntimeError("db down")
    monkeypatch.setattr(reply_guard.db, "has_confirmed_upcoming", boom)
    c = _ctx("Your appointment is booked.")
    assert reply_guard.should_block(c) is True   # fail closed — never let a false claim through


# --- verify() mutates the context ---------------------------------------------
def test_verify_replaces_reply_and_escalates(monkeypatch):
    monkeypatch.setattr(reply_guard.db, "has_confirmed_upcoming", lambda t, u: False)
    c = _ctx("Your appointment is booked for 5 PM!")
    reply_guard.verify(c)
    assert c.reply == reply_guard.SAFE_REPLY
    assert c.needs_human is True and c.guard_tripped is True


def test_verify_leaves_backed_reply_untouched():
    c = _ctx("Your appointment is booked for 5 PM!", booked=[99])
    original = c.reply
    reply_guard.verify(c)
    assert c.reply == original and c.guard_tripped is False


# --- availability guard -------------------------------------------------------
def _avail_ctx(reply, offered, checked=True):
    c = AgentContext(wa_user="966500000000", tenant_id=1)
    c.reply = reply
    c.availability_checked = checked
    c.offered_times = set(offered)
    return c


def test_time_mentions_parses_formats():
    assert {"17:00"} in reply_guard.time_mentions("How about 5 PM?")
    assert {"17:00"} in reply_guard.time_mentions("at 17:00")
    assert {"09:30"} in reply_guard.time_mentions("9:30 am works")
    # bare hour with no am/pm → both interpretations
    assert {"05:00", "17:00"} in reply_guard.time_mentions("come at 5:00")


def test_time_mentions_ignores_non_times():
    assert reply_guard.time_mentions("It costs 150 SAR for 30 minutes") == []
    assert reply_guard.time_mentions("on 2026-05-31") == []


def test_offered_time_is_allowed():
    c = _avail_ctx("Dr. Khalid is free at 5:00 PM and 6:00 PM.", {"17:00", "18:00"})
    assert reply_guard.should_block_availability(c) is False


def test_invented_time_is_blocked():
    c = _avail_ctx("I can offer you 5:00 PM or 8:00 PM.", {"17:00"})  # 20:00 not offered
    assert reply_guard.should_block_availability(c) is True


def test_patient_proposed_time_not_flagged():
    # Bot says the patient's requested 5 PM is taken — 17:00 isn't an offered slot, but the
    # patient proposed it, so it must not be flagged as invented.
    c = _avail_ctx("Sorry, 5 PM is taken, but 6:00 PM is open.", {"18:00"})
    assert reply_guard.should_block_availability(c, user_text="can I come at 5 PM?") is False


def test_no_check_means_no_policing():
    c = _avail_ctx("We're open from 9 AM to 11 PM.", set(), checked=False)
    assert reply_guard.should_block_availability(c) is False


def test_verify_corrects_invented_availability_with_real_slots():
    c = _avail_ctx("You can come at 8:00 PM.", {"17:00", "17:30"})
    reply_guard.verify(c, user_text="any evening slot?")
    assert c.guard_tripped is True and c.needs_human is True
    assert "5:00 PM" in c.reply and "5:30 PM" in c.reply        # real slots offered instead
    assert "8:00" not in c.reply


# --- language guard -----------------------------------------------------------
def test_detect_language():
    assert reply_guard.detect_language("Book me an appointment") == "en"
    assert reply_guard.detect_language("احجزلي موعد من فضلك") == "ar"
    assert reply_guard.detect_language("12345 :)") is None          # no letters → undecidable
    # Mixed: an Arabic sentence quoting an English name is still Arabic-dominant.
    assert reply_guard.detect_language("موعدك مع الدكتور خالد اليوم") == "ar"


def test_language_mismatch_flags_wrong_language():
    # Patient wrote Arabic, reply is pure English → mismatch.
    assert reply_guard.language_mismatch("احجزلي موعد", "Your appointment is booked.") is True
    # Patient wrote English, reply is Arabic → mismatch.
    assert reply_guard.language_mismatch("book me a slot", "تم الحجز مع الدكتور خالد") is True


def test_language_mismatch_allows_matching_and_mixed():
    # Same language → fine.
    assert reply_guard.language_mismatch("book me a slot", "You're booked for 5 PM.") is False
    assert reply_guard.language_mismatch("احجزلي موعد", "تم الحجز لك الساعة ٥ مساءً") is False
    # Arabic reply quoting English doctor/service names is NOT flagged.
    assert reply_guard.language_mismatch(
        "احجزلي موعد", "تم الحجز مع Dr. Khalid Al-Rashid، Dental Checkup الأحد 12:00 PM") is False
    # English reply quoting an Arabic name is NOT flagged.
    assert reply_guard.language_mismatch(
        "book me", "Booked with الدكتور Khalid for a Dental Checkup at 5 PM.") is False
    # Patient language undecidable (digits only) → never policed.
    assert reply_guard.language_mismatch("12345", "whatever the reply is") is False


# --- explicit language-switch request -----------------------------------------
def test_requested_language_detects_explicit_requests():
    cases = {
        "Can you speak urdu ?": "ur",
        "can you speak Arabic?": "ar",
        "Please reply in Hindi": "hi",
        "talk in english please": "en",
        "urdu please": "ur",
        "Urdu?": "ur",
        "switch to arabic": "ar",
        "reply in arabic please": "ar",
        "can you write in hindi": "hi",
        "تتكلم اردو؟": "ur",           # Arabic-script "do you speak Urdu?"
        "اردو": "ur",                   # bare language name
        "ممكن بالعربي": "ar",          # "can you, in Arabic"
    }
    for t, exp in cases.items():
        assert reply_guard.requested_language(t) == exp, t


def test_requested_language_ignores_non_requests():
    # A language merely MENTIONED (not requested of the bot) must not trigger a switch.
    for t in ["Do you have an Arabic-speaking doctor?",
              "I want to book an appointment",
              "How much is a cleaning?",
              "I don't know much about this",
              "english breakfast please",        # 'english' + 'please' but not adjacent
              ""]:
        assert reply_guard.requested_language(t) is None, t


def test_requested_language_none_when_two_languages_named():
    # Ambiguous ("switch from English to Urdu") → defer to normal mirroring.
    assert reply_guard.requested_language("should I write in english or urdu?") is None


def test_localize_picks_arabic_only_for_arabic_patient():
    assert reply_guard.localize("book me", "EN", "AR") == "EN"
    assert reply_guard.localize("احجزلي موعد", "EN", "AR") == "AR"
    assert reply_guard.localize("", "EN", "AR") == "EN"            # unknown → English default


def test_verify_safe_reply_is_localized_for_arabic(monkeypatch):
    monkeypatch.setattr(reply_guard.db, "has_confirmed_upcoming", lambda t, u: False)
    c = _ctx("تم الحجز لك الساعة ٥ مساءً")     # false Arabic booking claim
    reply_guard.verify(c, user_text="احجزلي موعد")
    assert c.reply == reply_guard.SAFE_REPLY_AR and c.guard_tripped is True


# --- Urdu language guard ------------------------------------------------------
def test_detect_language_urdu():
    # Urdu script is distinguished from Arabic by Urdu-specific letters.
    assert reply_guard.detect_language("مجھے اپائنٹمنٹ چاہیے") == "ur"
    assert reply_guard.detect_language("احجزلي موعد من فضلك") == "ar"
    # Romanised Urdu is spotted in Latin script; plain English is not.
    assert reply_guard.detect_language("mujhe appointment chahiye") == "ur"
    assert reply_guard.detect_language("appointment book ho gaya hai") == "ur"
    assert reply_guard.detect_language("Book me an appointment") == "en"


def test_language_mismatch_urdu():
    # Urdu-script patient, English / Arabic-script reply → mismatch.
    assert reply_guard.language_mismatch("مجھے اپائنٹمنٹ چاہیے", "You are booked.") is True
    assert reply_guard.language_mismatch("مجھے اپائنٹمنٹ چاہیے", "تم الحجز مع خالد") is True
    # Arabic patient, Urdu-script reply → mismatch (wrong Perso-Arabic language).
    assert reply_guard.language_mismatch("احجزلي موعد", "آپ کی اپائنٹمنٹ بک ہو گئی") is True
    # Romanised-Urdu patient, reply switched to Perso-Arabic script → mismatch.
    assert reply_guard.language_mismatch("mujhe appointment chahiye", "تم الحجز مع خالد") is True


def test_language_mismatch_urdu_allows_matching_and_mixed():
    # Urdu reply (with an English doctor/service name) to an Urdu patient → fine.
    assert reply_guard.language_mismatch(
        "مجھے اپائنٹمنٹ چاہیے",
        "آپ کی اپائنٹمنٹ Dr. Khalid کے ساتھ Dental Checkup بک ہو گئی ہے") is False
    # Romanised-Urdu patient getting a Latin reply is left alone (can't tell roman-Urdu apart).
    assert reply_guard.language_mismatch("mujhe appointment chahiye", "Sure, you're booked.") is False


def test_localize_picks_urdu():
    assert reply_guard.localize("mujhe appointment chahiye", "EN", "AR", ur="UR") == "UR"
    assert reply_guard.localize("مجھے اپائنٹمنٹ چاہیے", "EN", "AR", ur="UR") == "UR"
    # No Urdu string given → fall back to English, not Arabic.
    assert reply_guard.localize("mujhe appointment chahiye", "EN", "AR") == "EN"


def test_verify_safe_reply_is_localized_for_urdu(monkeypatch):
    monkeypatch.setattr(reply_guard.db, "has_confirmed_upcoming", lambda t, u: False)
    c = _ctx("آپ کی اپائنٹمنٹ بک ہو گئی ہے")   # false Urdu booking claim
    reply_guard.verify(c, user_text="mujhe appointment chahiye")
    assert c.reply == reply_guard.SAFE_REPLY_UR and c.guard_tripped is True


# --- Hindi language guard -----------------------------------------------------
def test_detect_language_hindi():
    # Devanagari is its own script → unambiguous Hindi.
    assert reply_guard.detect_language("मुझे अपॉइंटमेंट चाहिए") == "hi"
    assert reply_guard.detect_language("क्या कल कोई समय है?") == "hi"
    # Distinctively-Hindi romanised word flips the shared bucket to Hindi.
    assert reply_guard.detect_language("namaste, mujhe appointment chahiye") == "hi"
    # Shared romanised Indic (no Hindi-distinctive word) stays in the Urdu bucket.
    assert reply_guard.detect_language("mujhe appointment chahiye") == "ur"
    # Arabic / English are unaffected.
    assert reply_guard.detect_language("احجزلي موعد") == "ar"
    assert reply_guard.detect_language("Book me an appointment") == "en"


def test_language_mismatch_hindi():
    # Hindi-script patient, non-Devanagari reply → mismatch.
    assert reply_guard.language_mismatch("मुझे अपॉइंटमेंट चाहिए", "You're booked.") is True
    assert reply_guard.language_mismatch("मुझे अपॉइंटमेंट चाहिए", "تم الحجز مع خالد") is True
    assert reply_guard.language_mismatch("मुझे अपॉइंटमेंट चाहिए", "aap ki appointment ho gayi") is True
    # English / Arabic patient getting a Hindi (Devanagari) reply → mismatch.
    assert reply_guard.language_mismatch("book me", "आपकी अपॉइंटमेंट बुक हो गई है") is True
    assert reply_guard.language_mismatch("احجزلي موعد", "आपकी अपॉइंटमेंट बुक हो गई है") is True


def test_language_mismatch_hindi_allows_matching_and_mixed():
    # Hindi reply quoting an English doctor/service name → fine.
    assert reply_guard.language_mismatch(
        "मुझे अपॉइंटमेंट चाहिए",
        "आपकी अपॉइंटमेंट Dr. Khalid के साथ Dental Checkup बुक हो गई है") is False
    # Romanised-Hindi patient getting a Latin reply is left alone (can't tell apart from English).
    assert reply_guard.language_mismatch("namaste mujhe appointment chahiye", "Sure, booked!") is False


def test_localize_picks_hindi():
    assert reply_guard.localize("मुझे अपॉइंटमेंट चाहिए", "EN", "AR", ur="UR", hi="HI") == "HI"
    # No Hindi string given → fall back to English.
    assert reply_guard.localize("मुझे अपॉइंटमेंट चाहिए", "EN", "AR", ur="UR") == "EN"


def test_verify_safe_reply_is_localized_for_hindi(monkeypatch):
    monkeypatch.setattr(reply_guard.db, "has_confirmed_upcoming", lambda t, u: False)
    c = _ctx("आपकी अपॉइंटमेंट बुक हो गई है")   # false Hindi booking claim
    reply_guard.verify(c, user_text="मेरी अपॉइंटमेंट कन्फर्म करें")
    assert c.reply == reply_guard.SAFE_REPLY_HI and c.guard_tripped is True


# --- all-language guard (any language via langid) -----------------------------
def test_detect_language_latin_languages():
    # Long enough, confidently non-English Latin languages are identified.
    assert reply_guard.detect_language("Necesito una cita con el dentista urgente") == "es"
    assert reply_guard.detect_language("Quel est le prix du nettoyage dentaire?") == "fr"
    assert reply_guard.detect_language("Magkano ang pagpapalinis ng ngipin?") == "tl"
    # Short / ambiguous Latin text defaults to English (precision over recall).
    assert reply_guard.detect_language("Can I reschedule?") == "en"
    assert reply_guard.detect_language("Book me an appointment") == "en"


def test_detect_language_other_scripts():
    assert reply_guard.detect_language("আমার একটি অ্যাপয়েন্টমেন্ট দরকার") == "bn"   # Bengali
    assert reply_guard.detect_language("எனக்கு ஒரு சந்திப்பு வேண்டும்") == "ta"      # Tamil


def test_language_mismatch_latin_languages():
    es = "Necesito una cita con el dentista urgente"
    # Spanish patient, English reply → mismatch; Spanish reply → fine.
    assert reply_guard.language_mismatch(es, "Sure, you're booked for 5 PM tomorrow.") is True
    assert reply_guard.language_mismatch(es, "Claro, su cita está reservada para mañana.") is False
    # English patient, Spanish reply → mismatch.
    assert reply_guard.language_mismatch(
        "What are your opening hours please?", "Estamos abiertos de 9 a 11 todos los días.") is True
    # English patient, English reply (quoting an Arabic name) → fine.
    assert reply_guard.language_mismatch(
        "What are your opening hours please?", "We're open 9 to 11 with الدكتور Khalid.") is False


def test_language_mismatch_other_scripts():
    bn = "আমার একটি অ্যাপয়েন্টমেন্ট দরকার"
    # Bengali patient, English reply → mismatch; Bengali reply → fine.
    assert reply_guard.language_mismatch(bn, "You're all booked!") is True
    assert reply_guard.language_mismatch(bn, "আপনার অ্যাপয়েন্টমেন্ট বুক হয়ে গেছে") is False
    # English patient, Bengali reply → mismatch.
    assert reply_guard.language_mismatch("book me a slot please now", bn) is True


def test_localize_other_language_falls_back_to_english():
    es = "Necesito una cita con el dentista urgente"
    assert reply_guard.localize(es, "EN", "AR", ur="UR", hi="HI") == "EN"


def test_tagalog_override():
    # High-precision word override fixes short Tagalog the statistical classifier gets wrong.
    assert reply_guard.detect_language("Gusto ko po magpa-appointment sa dentista") == "tl"
    assert reply_guard.detect_language("Magkano ang pagpapalinis ng ngipin?") == "tl"
    assert reply_guard.detect_language("Salamat po sa tulong ninyo") == "tl"
    # No false positives: Spanish / French (incl. French "sa") / English stay themselves.
    assert reply_guard.detect_language("Sa maison et sa voiture sont grandes") != "tl"
    assert reply_guard.detect_language("Book me an appointment") == "en"
    assert reply_guard.detect_language("Necesito una cita con el dentista urgente") == "es"


def test_language_mismatch_tagalog():
    tl = "Gusto ko po magpa-appointment sa dentista"
    # Tagalog patient, English reply → mismatch; Tagalog reply → fine.
    assert reply_guard.language_mismatch(tl, "Sure, you're booked for tomorrow!") is True
    assert reply_guard.language_mismatch(
        tl, "Sige po, naka-book na po kayo bukas ng 5 PM kay Dr. Khalid.") is False
