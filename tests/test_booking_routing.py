"""Tool-level routing rules that don't touch the DB: right-doctor-for-service (specialty),
service-not-found recovery, and lab/imaging services that need no specific doctor.
Uses a fake connector so these run without Postgres."""
from datetime import date, datetime, time, timedelta

from app.config import TZ
from app.tools import AgentContext, dispatch

CLINIC = {
    "doctors": [
        {"name": "Dr. Khalid Al-Otaibi", "specialty": "General Medicine",
         "available_days": ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday",
                            "Friday", "Saturday"], "available_hours": "9:00 AM - 11:00 PM"},
        {"name": "Dr. Hassan Al-Qahtani", "specialty": "Dentist",
         "available_days": ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday",
                            "Friday", "Saturday"], "available_hours": "9:00 AM - 11:00 PM"},
    ],
    "services": [
        {"name": "Dental Cleaning", "price_sar": 400, "duration_min": 30, "specialty": "Dentist"},
        {"name": "Lab Test - Blood Sugar", "price_sar": 50, "duration_min": 15},
    ],
}

_SLOT = datetime.combine(date.today() + timedelta(days=2), time(17, 0), tzinfo=TZ)


class _FakeConn:
    """Every doctor is free at _SLOT on its date; nothing else. No DB, no lead-time logic."""
    def available_slots(self, doctor, on, duration_min, now):
        return [_SLOT] if on == _SLOT.date() else []


def _ctx():
    return AgentContext(wa_user="966500000001", tenant_id=1, clinic_data=CLINIC,
                        connector=_FakeConn())


def test_wrong_specialty_blocks_and_suggests_the_right_doctor():
    args = {"doctor": "Khalid", "service": "Dental Cleaning", "date": _SLOT.date().isoformat()}
    out = dispatch("check_availability", args, _ctx())
    assert out.get("error") == "wrong_specialty", out
    assert "Dr. Hassan Al-Qahtani" in out["suggested_doctors"]

    book = dispatch("book_appointment", {"patient_name": "A", **args, "time": "17:00"}, _ctx())
    assert book.get("error") == "wrong_specialty", book


def test_right_specialty_passes_through():
    out = dispatch("check_availability",
                   {"doctor": "Hassan", "service": "Dental Cleaning",
                    "date": _SLOT.date().isoformat()}, _ctx())
    assert "error" not in out, out
    assert out["doctor"] == "Dr. Hassan Al-Qahtani"
    assert "17:00" in out["available_times"]


def test_service_not_found_returns_the_catalogue():
    out = dispatch("check_availability",
                   {"doctor": "Hassan", "service": "teleportation",
                    "date": _SLOT.date().isoformat()}, _ctx())
    assert out.get("error") == "service_not_found", out
    assert "Dental Cleaning" in out["available_services"]


def test_lab_service_needs_no_doctor():
    # No doctor passed; the lab service should still return clinic-wide slots.
    out = dispatch("check_availability",
                   {"service": "Lab Test - Blood Sugar", "date": _SLOT.date().isoformat()}, _ctx())
    assert "error" not in out, out
    assert out["no_doctor_needed"] is True
    assert out["doctor"] is None
    assert "17:00" in out["available_times"]


def test_doctor_required_for_clinical_service_when_omitted():
    out = dispatch("check_availability",
                   {"service": "Dental Cleaning", "date": _SLOT.date().isoformat()}, _ctx())
    assert out.get("error") == "doctor_required", out
    assert "Dr. Hassan Al-Qahtani" in out["available_doctors"]
