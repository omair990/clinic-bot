from datetime import date, datetime, time, timedelta

from app.config import TZ
from app import scheduling as s


def _next_named_day(name: str, start: date) -> date:
    d = start
    for _ in range(8):
        if d.strftime("%A") == name:
            return d
        d += timedelta(days=1)
    raise AssertionError(f"no {name} found")


def test_find_doctor_by_fragment_and_specialty():
    assert s.find_doctor("Khalid")["name"] == "Dr. Khalid Al-Otaibi"
    assert s.find_doctor("dr. khalid al-otaibi")["name"] == "Dr. Khalid Al-Otaibi"
    assert s.find_doctor("dentist")["specialty"] == "Dentist"
    assert s.find_doctor("nobody") is None


def test_find_service():
    assert s.find_service("general consultation")["price_sar"] == 150
    assert s.find_service("cleaning")["name"] == "Dental Cleaning"
    assert s.find_service("rocket science") is None


def test_parse_windows():
    assert s.parse_windows("10:00 AM - 1:00 PM, 5:00 PM - 9:00 PM") == [
        (time(10, 0), time(13, 0)),
        (time(17, 0), time(21, 0)),
    ]


def test_parse_date_and_clock():
    today = date(2026, 6, 1)
    assert s.parse_date("today", today) == today
    assert s.parse_date("tomorrow", today) == date(2026, 6, 2)
    assert s.parse_date("2026-06-10", today) == date(2026, 6, 10)
    assert s.parse_date("nonsense", today) is None
    assert s.parse_clock("17:00") == time(17, 0)
    assert s.parse_clock("5:00 PM") == time(17, 0)
    assert s.parse_clock("5pm") == time(17, 0)


def test_available_slots_on_working_day():
    doctor = s.find_doctor("Khalid")  # works Sundays, 10-13 and 17-21
    sunday = _next_named_day("Sunday", date(2026, 6, 1))
    now = datetime.combine(sunday, time(7, 0), tzinfo=TZ)  # lead time clears 10:00
    slots = s.available_slots(doctor, sunday, 20, booked=[], now=now)
    starts = {sl.strftime("%H:%M") for sl in slots}
    assert "10:00" in starts
    assert "17:00" in starts
    # 15-min steps from 10:00; last 20-min slot that fits before 13:00 is 12:30
    assert "12:30" in starts
    assert "12:45" not in starts
    assert "13:00" not in starts


def test_available_slots_excludes_booked_overlap():
    doctor = s.find_doctor("Khalid")
    sunday = _next_named_day("Sunday", date(2026, 6, 1))
    now = datetime.combine(sunday, time(7, 0), tzinfo=TZ)
    booked = [(
        datetime.combine(sunday, time(10, 0), tzinfo=TZ),
        datetime.combine(sunday, time(10, 20), tzinfo=TZ),
    )]
    starts = {sl.strftime("%H:%M") for sl in s.available_slots(doctor, sunday, 20, booked, now)}
    assert "10:00" not in starts   # exact overlap
    assert "10:15" not in starts   # 10:15-10:35 overlaps 10:00-10:20
    assert "10:30" in starts       # clear of the booking


def test_available_slots_respects_lead_time():
    doctor = s.find_doctor("Khalid")
    sunday = _next_named_day("Sunday", date(2026, 6, 1))
    # "Now" is 11:30 the same day -> 2h lead pushes earliest bookable to 13:30,
    # so all morning slots are gone, evening (17:00+) remains.
    now = datetime.combine(sunday, time(11, 30), tzinfo=TZ)
    starts = {sl.strftime("%H:%M") for sl in s.available_slots(doctor, sunday, 20, [], now)}
    assert not any(t < "13:30" for t in starts)
    assert "17:00" in starts


def test_no_slots_on_non_working_day():
    doctor = s.find_doctor("Sara")  # Sun/Tue/Thu only
    friday = _next_named_day("Friday", date(2026, 6, 1))
    now = datetime.combine(friday, time(7, 0), tzinfo=TZ)
    assert s.available_slots(doctor, friday, 30, [], now) == []


def test_next_available_returns_working_days_in_order_within_horizon():
    doctor = s.find_doctor("Khalid")
    monday = _next_named_day("Monday", date(2026, 6, 1))
    now = datetime.combine(monday, time(0, 1), tzinfo=TZ)
    days = s.next_available_days(doctor, 20, booked=[], now=now, start=monday)
    assert days, "should find openings within the month"
    assert len(days) <= 3                            # default max_days cap
    dates = [d for d, _ in days]
    assert dates == sorted(dates)                    # chronological
    for d, slots in days:
        assert s.doctor_works_on(doctor, d)          # only real working days
        assert (d - monday).days <= 30               # within the month horizon
        assert slots                                 # each has bookable times
    # The first opening is the earliest working day on/after the start — none skipped.
    cur = monday
    while not s.doctor_works_on(doctor, cur):
        cur += timedelta(days=1)
    assert dates[0] == cur


def test_next_available_empty_when_no_working_day_in_horizon():
    doctor = s.find_doctor("Khalid")
    # Anchor on the next day this doctor does NOT work; a 0-day horizon checks only that
    # day, so there is no opening -> empty list (no crash, no guessing).
    start = _next_named_day("Monday", date(2026, 6, 1))
    while s.doctor_works_on(doctor, start):
        start += timedelta(days=1)
    now = datetime.combine(start, time(7, 0), tzinfo=TZ)
    assert s.next_available_days(doctor, 20, [], now, start=start, horizon_days=0) == []


# --- fuzzy / alias matching, specialty + lab helpers ----------------------------------

_SERVICES = [
    {"name": "Dental Cleaning", "price_sar": 400, "duration_min": 45, "specialty": "Dentist"},
    {"name": "Lab Test - Blood Sugar", "price_sar": 50, "duration_min": 15,
     "aliases": ["فحص السكر", "سكر"]},
]
_DOCTORS = [
    {"name": "Dr. Khalid Al-Otaibi", "specialty": "General Medicine",
     "available_days": ["Sunday"], "available_hours": "10:00 AM - 1:00 PM"},
    {"name": "Dr. Hassan Al-Qahtani", "specialty": "Dentist",
     "available_days": ["Monday"], "available_hours": "10:00 AM - 1:00 PM",
     "aliases": ["حسن القحطاني"]},
]


def test_find_service_fuzzy_partial_and_typo():
    assert s.find_service("cleaning", _SERVICES)["name"] == "Dental Cleaning"
    assert s.find_service("dental cleaaning", _SERVICES)["name"] == "Dental Cleaning"  # typo
    assert s.find_service("rocket science", _SERVICES) is None                          # no match


def test_find_matches_via_alias_and_cross_script():
    assert s.find_service("فحص السكر", _SERVICES)["name"] == "Lab Test - Blood Sugar"
    assert s.find_doctor("حسن القحطاني", _DOCTORS)["name"] == "Dr. Hassan Al-Qahtani"


# Regression: two services sharing a generic leading word ("تحليل" = test/analysis) must NOT
# both collapse onto whichever is listed first. The patient asked for "تحليل سكر" (Blood
# Sugar) but the booking was recorded as "تحليل دم شامل" (CBC) because a shared word-token
# substring-matched the earlier-listed service. Resolve on the distinguishing word instead.
_AR_SERVICES = [
    {"name": "تحليل دم شامل", "price_sar": 80},   # CBC — listed first
    {"name": "تحليل سكر", "price_sar": 50},        # Blood Sugar
]


def test_shared_category_word_resolves_to_distinguishing_service():
    assert s.find_service("تحليل سكر", _AR_SERVICES)["name"] == "تحليل سكر"
    assert s.find_service("تحليل دم شامل", _AR_SERVICES)["name"] == "تحليل دم شامل"
    assert s.find_service("سكر", _AR_SERVICES)["name"] == "تحليل سكر"


def test_prefix_name_does_not_beat_more_specific_one():
    # A service whose name is a prefix word of another must not win the longer query.
    rows = [{"name": "استشارة"}, {"name": "استشارة أطفال"}]
    assert s.find_service("استشارة أطفال", rows)["name"] == "استشارة أطفال"


def test_find_doctor_strips_honorifics_and_tolerates_typos():
    assert s.find_doctor("dr. khalid", _DOCTORS)["name"] == "Dr. Khalid Al-Otaibi"
    assert s.find_doctor("kalid", _DOCTORS)["name"] == "Dr. Khalid Al-Otaibi"   # token typo
    assert s.find_doctor("nobody xyz", _DOCTORS) is None


def test_service_requires_doctor_inference_and_override():
    assert s.service_requires_doctor({"name": "Dental Cleaning"}) is True
    assert s.service_requires_doctor({"name": "Lab Test - Blood Sugar"}) is False
    assert s.service_requires_doctor({"name": "فحص السكر"}) is False
    assert s.service_requires_doctor({"name": "Lab Test", "requires_doctor": True}) is True
    assert s.service_requires_doctor({"name": "Consultation", "requires_doctor": False}) is False


def test_specialty_compatibility():
    dentist, gp = _DOCTORS[1], _DOCTORS[0]
    assert s.service_specialty(_SERVICES[0]) == "Dentist"
    assert s.service_specialty(_SERVICES[1]) == ""
    assert s.doctor_matches_specialty(dentist, "Dentist")
    assert s.doctor_matches_specialty({"specialty": "Dentistry"}, "Dentist")  # substring
    assert not s.doctor_matches_specialty(gp, "Dentist")
    assert s.doctor_matches_specialty(gp, "")   # no requirement -> always compatible
