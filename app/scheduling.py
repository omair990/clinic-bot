"""Slot generation and availability logic.

Pure functions over clinic config + already-booked intervals. No DB or network here,
so it is fully unit-testable. All datetimes returned are timezone-aware (clinic TZ).
"""
from datetime import date as date_cls
from datetime import datetime, time, timedelta

from app.config import (
    BOOKING_LEAD_HOURS,
    CLINIC_DATA,
    SLOT_GRANULARITY_MIN,
    TZ,
)

DOCTORS = CLINIC_DATA["doctors"]
SERVICES = CLINIC_DATA["services"]


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def find_doctor(query: str, doctors: list[dict] | None = None) -> dict | None:
    """Match a doctor by full name or a distinctive fragment (e.g. 'khalid', 'dentist').

    `doctors` defaults to the global clinic config; pass a tenant's list for isolation.
    """
    if not query:
        return None
    doctors = DOCTORS if doctors is None else doctors
    q = _norm(query)
    for doc in doctors:
        if _norm(doc["name"]) == q:
            return doc
    for doc in doctors:
        name = _norm(doc["name"])
        if q in name or name in q or q in _norm(doc["specialty"]):
            return doc
    return None


def find_service(query: str, services: list[dict] | None = None) -> dict | None:
    if not query:
        return None
    services = SERVICES if services is None else services
    q = _norm(query)
    for svc in services:
        if _norm(svc["name"]) == q:
            return svc
    for svc in services:
        if q in _norm(svc["name"]) or _norm(svc["name"]) in q:
            return svc
    return None


def _parse_time(token: str) -> time:
    return datetime.strptime(token.strip().upper().replace(".", ""), "%I:%M %p").time()


def parse_windows(spec: str) -> list[tuple[time, time]]:
    """'10:00 AM - 1:00 PM, 5:00 PM - 9:00 PM' -> [(10:00, 13:00), (17:00, 21:00)]."""
    windows = []
    for chunk in spec.split(","):
        if "-" not in chunk:
            continue
        start_s, end_s = chunk.split("-", 1)
        try:
            windows.append((_parse_time(start_s), _parse_time(end_s)))
        except ValueError:
            continue
    return windows


def doctor_works_on(doctor: dict, on: date_cls) -> bool:
    weekday = on.strftime("%A")
    return any(weekday.lower() == d.lower() for d in doctor.get("available_days", []))


def available_slots(doctor: dict, on: date_cls, duration_min: int,
                    booked: list[tuple[datetime, datetime]],
                    now: datetime) -> list[datetime]:
    """Bookable start times for `doctor` on `on` for a `duration_min` service.

    Excludes past times, slots inside the booking lead-time window, and any slot whose
    [start, end) overlaps an already-booked interval. Slots step by SLOT_GRANULARITY_MIN.
    """
    if not doctor_works_on(doctor, on):
        return []

    earliest = now + timedelta(hours=BOOKING_LEAD_HOURS)
    step = timedelta(minutes=SLOT_GRANULARITY_MIN)
    duration = timedelta(minutes=duration_min)
    slots: list[datetime] = []

    for win_start, win_end in parse_windows(doctor.get("available_hours", "")):
        cursor = datetime.combine(on, win_start, tzinfo=TZ)
        window_close = datetime.combine(on, win_end, tzinfo=TZ)
        while cursor + duration <= window_close:
            slot_end = cursor + duration
            if cursor >= earliest and not _overlaps(cursor, slot_end, booked):
                slots.append(cursor)
            cursor += step
    return slots


def _overlaps(start: datetime, end: datetime,
              intervals: list[tuple[datetime, datetime]]) -> bool:
    return any(start < b_end and end > b_start for b_start, b_end in intervals)


def day_bounds(on: date_cls) -> tuple[datetime, datetime]:
    """[00:00, next-day 00:00) in clinic TZ — used to fetch a day's bookings."""
    start = datetime.combine(on, time(0, 0), tzinfo=TZ)
    return start, start + timedelta(days=1)


def parse_date(s: str, today: date_cls) -> date_cls | None:
    """Accept ISO 'YYYY-MM-DD' or the words today/tomorrow."""
    s = s.strip().lower()
    if s in ("today", "اليوم"):
        return today
    if s in ("tomorrow", "غدا", "غداً", "بكرة"):
        return today + timedelta(days=1)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_clock(s: str) -> time | None:
    """Accept '17:00', '5:00 PM', '5pm', '5 pm'."""
    s = s.strip().upper().replace(".", "")
    for fmt in ("%H:%M", "%I:%M %p", "%I %p", "%I:%M%p", "%I%p"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    return None
