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
