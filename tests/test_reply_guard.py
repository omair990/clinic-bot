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
