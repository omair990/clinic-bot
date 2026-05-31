"""Unit tests for dashboard status-change patient notifications (no DB/network)."""
from app.notifications import appointment_status_message


def test_cancelled_message():
    m = appointment_status_message("cancelled", "Dental Cleaning", "Dr. Khalid",
                                   "Sunday 31 May, 06:00 PM", "Al-Shifa")
    assert "cancelled" in m
    assert "Dental Cleaning with Dr. Khalid" in m
    assert "Al-Shifa" in m and "rebook" in m


def test_completed_message():
    m = appointment_status_message("completed", "Consult", "Dr. Sara",
                                   "Monday 01 June, 10:00 AM", "Al-Shifa")
    assert "Thank you" in m and "Al-Shifa" in m


def test_message_without_service_doctor_uses_generic_subject():
    m = appointment_status_message("cancelled", None, None, "tomorrow", "Clinic")
    assert "your appointment" in m


def test_no_message_for_non_notify_statuses():
    assert appointment_status_message("confirmed", "S", "D", "x", "C") is None
    assert appointment_status_message("no_show", "S", "D", "x", "C") is None
