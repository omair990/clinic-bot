"""Slot generation and availability logic.

Pure functions over clinic config + already-booked intervals. No DB or network here,
so it is fully unit-testable. All datetimes returned are timezone-aware (clinic TZ).
"""
from datetime import date as date_cls
from datetime import datetime, time, timedelta
from difflib import SequenceMatcher

from app.config import (
    BOOKING_LEAD_HOURS,
    CLINIC_DATA,
    SLOT_GRANULARITY_MIN,
    TZ,
)

DOCTORS = CLINIC_DATA["doctors"]
SERVICES = CLINIC_DATA["services"]


def _norm(s: str) -> str:
    # Honorifics/titles carry no identifying signal and differ by language ("Dr.", "د.",
    # "دكتور"), so strip them before matching to avoid them dominating a fuzzy score.
    s = (s or "").lower()
    for title in ("dr.", "dr ", "doctor", "د.", "د ", "دكتور", "الدكتور"):
        s = s.replace(title, " ")
    return "".join(ch for ch in s if ch.isalnum())


# Fuzzy-match acceptance threshold (0..1). High enough to avoid cross-service false
# positives, low enough to absorb typos and word-order/spelling variants in one script.
_FUZZY_MIN = 0.78


def _aliases(row: dict) -> list[str]:
    """A row's alternative names (e.g. Arabic terms a clinic added). Optional — absent on
    most rows. Lets cross-script queries match without a translation step."""
    raw = row.get("aliases")
    if isinstance(raw, str):
        return [a.strip() for a in raw.split(",") if a.strip()]
    return [str(a) for a in raw] if isinstance(raw, list) else []


def _best_match(query: str, rows: list[dict], extra_keys: tuple = ()) -> dict | None:
    """Resolve `query` to one row by: exact normalized name/alias → substring either way →
    fuzzy ratio over name+aliases(+extra_keys, e.g. specialty). Returns None below threshold
    so callers can surface the real list instead of guessing wrong."""
    if not query or not rows:
        return None
    q = _norm(query)
    if not q:
        return None

    def cands(row: dict) -> list[str]:
        vals = [row.get("name", "")] + _aliases(row) + [row.get(k, "") for k in extra_keys]
        out: list[str] = []
        for v in vals:
            whole = _norm(v)
            if whole:
                out.append(whole)
            # Also match individual words, so a typo on part of a name ("kalid" for the
            # "Khalid" in "Dr. Khalid Al-Otaibi") still resolves. Skip tiny tokens ("al").
            for tok in str(v).split():
                t = _norm(tok)
                if len(t) >= 3:
                    out.append(t)
        return out

    for row in rows:                                   # exact
        if q in cands(row):
            return row
    for row in rows:                                   # substring either direction
        if any(q in c or c in q for c in cands(row)):
            return row
    best, best_score = None, 0.0                       # fuzzy fallback (same-script typos)
    for row in rows:
        score = max((SequenceMatcher(None, q, c).ratio() for c in cands(row)), default=0.0)
        if score > best_score:
            best, best_score = row, score
    return best if best_score >= _FUZZY_MIN else None


def find_doctor(query: str, doctors: list[dict] | None = None) -> dict | None:
    """Match a doctor by full name, alias, specialty, or a close/typo'd fragment.

    `doctors` defaults to the global clinic config; pass a tenant's list for isolation.
    """
    doctors = DOCTORS if doctors is None else doctors
    return _best_match(query, doctors, extra_keys=("specialty",))


def find_service(query: str, services: list[dict] | None = None) -> dict | None:
    services = SERVICES if services is None else services
    return _best_match(query, services)


# Lightweight category inference: services whose name reads like a lab/imaging test don't
# need a clinician chosen. A clinic can override either way with an explicit `requires_doctor`.
_LAB_HINTS = ("lab", "test", "screen", "blood", "x-ray", "xray", "scan", "sample", "urine",
              "تحليل", "فحص", "مختبر", "أشعة", "اشعة", "عينة")


def service_requires_doctor(service: dict) -> bool:
    """Whether booking this service needs a specific doctor. Explicit `requires_doctor`
    wins; otherwise lab/imaging-type services default to False, everything else True."""
    explicit = service.get("requires_doctor")
    if isinstance(explicit, bool):
        return explicit
    name = (service.get("name") or "").lower()
    return not any(h in name for h in _LAB_HINTS)


def service_specialty(service: dict) -> str:
    """The specialty a service should be performed by, if the clinic declared one
    (e.g. a 'Dental Cleaning' tagged 'Dentist'). Empty string when unspecified."""
    return str(service.get("specialty") or "").strip()


def doctor_matches_specialty(doctor: dict, specialty: str) -> bool:
    """Loose specialty compatibility — substring either way so 'Dentist' matches
    'Dental', 'dentistry', etc. Always True when no specialty is required."""
    if not specialty:
        return True
    a, b = _norm(doctor.get("specialty", "")), _norm(specialty)
    return bool(a) and bool(b) and (a in b or b in a)


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


def next_available_days(doctor: dict, duration_min: int,
                        booked: list[tuple[datetime, datetime]], now: datetime,
                        start: date_cls, horizon_days: int = 30,
                        max_days: int = 3) -> list[tuple[date_cls, list[datetime]]]:
    """Scan from `start` up to `horizon_days` ahead (inclusive) and return the first
    `max_days` working days that have free slots, as (date, slots).

    Answers "when is the doctor next free?" deterministically instead of the model
    guessing dates or only ever checking today/tomorrow. `booked` must cover the whole
    [start, start+horizon_days] window; `_overlaps` only matches same-day intervals, so
    passing the full window's bookings is safe.
    """
    found: list[tuple[date_cls, list[datetime]]] = []
    for offset in range(horizon_days + 1):
        on = start + timedelta(days=offset)
        slots = available_slots(doctor, on, duration_min, booked, now)
        if slots:
            found.append((on, slots))
            if len(found) >= max_days:
                break
    return found


def _overlaps(start: datetime, end: datetime,
              intervals: list[tuple[datetime, datetime]]) -> bool:
    return any(start < b_end and end > b_start for b_start, b_end in intervals)


def day_bounds(on: date_cls) -> tuple[datetime, datetime]:
    """[00:00, next-day 00:00) in clinic TZ — used to fetch a day's bookings."""
    start = datetime.combine(on, time(0, 0), tzinfo=TZ)
    return start, start + timedelta(days=1)


_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4,
    "saturday": 5, "sunday": 6,
    "الاثنين": 0, "الإثنين": 0, "الثلاثاء": 1, "الأربعاء": 2, "الاربعاء": 2,
    "الخميس": 3, "الجمعة": 4, "السبت": 5, "الأحد": 6, "الاحد": 6,
}


def parse_date(s: str, today: date_cls) -> date_cls | None:
    """Accept ISO 'YYYY-MM-DD', today/tomorrow, or a weekday name ('sunday',
    'this sunday', 'next monday') resolved to its next occurrence."""
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
    # Weekday names: compute the next occurrence (deterministic — don't rely on the model).
    nxt = "next" in s
    key = s.replace("this", "").replace("next", "").replace("on", "").strip()
    if key in _WEEKDAYS:
        delta = (_WEEKDAYS[key] - today.weekday()) % 7
        if delta == 0 and nxt:
            delta = 7
        return today + timedelta(days=delta)
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
