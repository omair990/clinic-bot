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
