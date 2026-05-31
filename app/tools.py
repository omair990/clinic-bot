"""Agent tools: JSON-schema specs the model sees + Python handlers that run them.

Handlers take (args: dict, ctx: AgentContext) and return a JSON-serialisable dict that
is fed back to the model. Side effects (bookings, escalations) are recorded on ctx so the
webhook can act on them (notify staff, log intent) after the turn completes.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app import db
from app.config import BOOKING_LEAD_HOURS, TZ
from app.llm import ToolSpec
from app.scheduling import (
    available_slots,
    day_bounds,
    doctor_works_on,
    find_doctor,
    find_service,
    parse_clock,
    parse_date,
)

log = logging.getLogger(__name__)

DEFAULT_DURATION_MIN = 30


def _field_value(extra: dict, field: dict) -> str:
    """Look up a field's value by key OR label, case-insensitively — models pass
    either the key or the human label as the dict key."""
    lower = {str(k).lower(): v for k, v in extra.items()}
    for cand in (field.get("key"), field.get("label")):
        if not cand:
            continue
        v = extra.get(cand)
        if v is None:
            v = lower.get(str(cand).lower())
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def check_booking_fields(clinic_data: dict, extra: dict | None) -> dict | None:
    """Validate clinic-specific intake fields. Returns an error dict (telling the
    model what's still needed) or None if all good.

    Each field in clinic_data['booking_fields'] is {key, label, required?, options?}.
    """
    fields = (clinic_data or {}).get("booking_fields") or []
    extra = extra if isinstance(extra, dict) else {}
    missing = [f.get("label") or f.get("key") for f in fields
               if f.get("required") and not _field_value(extra, f)]
    if missing:
        return {"error": "missing_information", "needed": missing,
                "hint": "Ask the patient for these before booking."}
    for f in fields:
        opts = f.get("options")
        val = _field_value(extra, f)
        if opts and val and val.lower() not in [str(o).lower() for o in opts]:
            return {"error": "invalid_value", "field": f.get("label") or f.get("key"),
                    "allowed": opts}
    return None


@dataclass
class AgentContext:
    wa_user: str
    tenant_id: int = 0
    clinic_data: dict = field(default_factory=dict)
    reply: str = ""
    needs_human: bool = False
    emergency: bool = False
    escalation_reason: str | None = None
    booked_ids: list[int] = field(default_factory=list)
    changed_ids: list[int] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    # The patient's open no-show follow-up (missed appointment we're recovering), if any.
    no_show: dict | None = None
    # A pending post-visit review request awaiting the patient's star rating, if any.
    review: dict | None = None

    @property
    def doctors(self) -> list[dict]:
        return self.clinic_data.get("doctors", []) if self.clinic_data else []

    @property
    def services(self) -> list[dict]:
        return self.clinic_data.get("services", []) if self.clinic_data else []

    def derived_intent(self) -> str:
        if self.emergency:
            return "emergency"
        if self.needs_human:
            return "handover"
        if self.booked_ids or self.changed_ids:
            return "appointment"
        return "chat"


def _now() -> datetime:
    return datetime.now(TZ)


def _fmt(dt: datetime) -> str:
    return dt.astimezone(TZ).strftime("%A %Y-%m-%d %H:%M")


# --- Tool specs exposed to the model ---

TOOL_SPECS: list[ToolSpec] = [
    ToolSpec("list_services", "List clinic services with prices (SAR) and durations.",
             {"type": "object", "properties": {}}),
    ToolSpec("list_doctors", "List doctors, their specialty, and the days they work.",
             {"type": "object", "properties": {
                 "specialty": {"type": "string", "description": "Optional filter, e.g. 'dentist'."}}}),
    ToolSpec("check_availability",
             "Return bookable start times for a doctor on a date. Call before offering any time.",
             {"type": "object", "properties": {
                 "doctor": {"type": "string", "description": "Doctor name or fragment, e.g. 'Khalid'."},
                 "date": {"type": "string", "description": "YYYY-MM-DD, or 'today'/'tomorrow'."},
                 "service": {"type": "string", "description": "Service name (sets the slot length)."}},
              "required": ["doctor", "date"]}),
    ToolSpec("book_appointment",
             "Reserve a specific slot. Only use a time confirmed free by check_availability. "
             "Collect the patient's name and contact phone number before calling.",
             {"type": "object", "properties": {
                 "patient_name": {"type": "string"},
                 "phone": {"type": "string", "description": "ONLY if the patient gives a "
                           "different contact number; otherwise leave empty and their "
                           "WhatsApp number is used automatically."},
                 "doctor": {"type": "string"},
                 "service": {"type": "string"},
                 "date": {"type": "string", "description": "YYYY-MM-DD or 'today'/'tomorrow'."},
                 "time": {"type": "string", "description": "Start time, e.g. '17:00' or '5:00 PM'."},
                 "extra": {"type": "object", "description": "Clinic-specific intake fields "
                           "(keys/labels listed in the system prompt), e.g. payment method."}},
              "required": ["patient_name", "doctor", "service", "date", "time"]}),
    ToolSpec("get_faqs",
             "Clinic FAQs: insurance, parking, home service, prescription refills, "
             "cancellation/reschedule policy, treating non-Saudis.",
             {"type": "object", "properties": {}}),
    ToolSpec("get_my_appointments", "List this patient's upcoming appointments (with ids).",
             {"type": "object", "properties": {}}),
    ToolSpec("reschedule_appointment", "Move an existing appointment to a new date/time.",
             {"type": "object", "properties": {
                 "appointment_id": {"type": "integer"},
                 "date": {"type": "string"},
                 "time": {"type": "string"}},
              "required": ["appointment_id", "date", "time"]}),
    ToolSpec("cancel_appointment", "Cancel an existing appointment by id.",
             {"type": "object", "properties": {"appointment_id": {"type": "integer"}},
              "required": ["appointment_id"]}),
    ToolSpec("escalate_to_human",
             "Flag the conversation for clinic staff (emergency, complaint, or out-of-scope).",
             {"type": "object", "properties": {
                 "reason": {"type": "string"},
                 "emergency": {"type": "boolean", "description": "True for medical emergencies."}},
              "required": ["reason"]}),
    ToolSpec("record_review",
             "ONLY when a REVIEW REQUEST is pending (see system prompt): record the patient's "
             "1-5 star rating of their recent visit, plus any comment they gave.",
             {"type": "object", "properties": {
                 "appointment_id": {"type": "integer", "description": "The visit's appointment "
                                    "id shown in the REVIEW REQUEST note."},
                 "rating": {"type": "integer", "description": "1 to 5 (5 = excellent)."},
                 "comment": {"type": "string", "description": "Optional free-text feedback."}},
              "required": ["appointment_id", "rating"]}),
    ToolSpec("record_no_show_response",
             "ONLY when a NO-SHOW FOLLOW-UP is in progress (see system prompt): log how the "
             "patient who missed their appointment responded — their chosen outcome and/or the "
             "reason they missed. Call this in addition to actually rescheduling/cancelling.",
             {"type": "object", "properties": {
                 "appointment_id": {"type": "integer", "description": "The missed appointment id "
                                    "shown in the NO-SHOW FOLLOW-UP note."},
                 "outcome": {"type": "string", "enum": ["reschedule", "call", "cancel"],
                             "description": "What the patient chose."},
                 "reason": {"type": "string", "enum": ["forgot", "busy", "emergency", "price",
                            "other_clinic", "other"],
                            "description": "Why they missed, mapped to the closest option."}},
              "required": ["appointment_id"]}),
]


# --- Handlers ---

def _list_services(args: dict, ctx: AgentContext) -> dict:
    return {"services": [
        {"name": s["name"], "price_sar": s["price_sar"], "duration_min": s["duration_min"]}
        for s in ctx.services]}


def _list_doctors(args: dict, ctx: AgentContext) -> dict:
    spec = (args.get("specialty") or "").lower().strip()
    docs = ctx.doctors
    if spec:
        docs = [d for d in ctx.doctors if spec in d["specialty"].lower()] or ctx.doctors
    return {"doctors": [
        {"name": d["name"], "specialty": d["specialty"],
         "available_days": d["available_days"], "available_hours": d["available_hours"]}
        for d in docs]}


def _check_availability(args: dict, ctx: AgentContext) -> dict:
    doctor = find_doctor(args.get("doctor", ""), ctx.doctors)
    if not doctor:
        return {"error": "doctor_not_found",
                "available_doctors": [d["name"] for d in ctx.doctors]}
    on = parse_date(args.get("date", ""), _now().date())
    if not on:
        return {"error": "bad_date", "hint": "Use YYYY-MM-DD or 'today'/'tomorrow'."}
    service = find_service(args.get("service", ""), ctx.services) if args.get("service") else None
    duration = service["duration_min"] if service else DEFAULT_DURATION_MIN

    now = _now()
    start, end = day_bounds(on)
    booked = db.booked_intervals(ctx.tenant_id, doctor["name"], start, end)
    slots = available_slots(doctor, on, duration, booked, now)
    result = {
        "doctor": doctor["name"],
        "date": on.isoformat(),
        "day": on.strftime("%A"),          # weekday name — use this, don't compute it
        "date_label": on.strftime("%A, %d %B %Y"),
        "service": service["name"] if service else None,
        "slot_duration_min": duration,
        "available_times": [s.strftime("%H:%M") for s in slots[:12]],
        "more_available": len(slots) > 12,
        "note": None if slots else "No free slots that day — suggest another day.",
        "booking_lead_hours": BOOKING_LEAD_HOURS,
    }
    # Today only: times before now + lead-time can't be booked even though the clinic is
    # open then. Surface this so the bot explains "that's too soon" instead of wrongly
    # telling the patient the clinic/doctor isn't available at that hour.
    if on == now.date() and doctor_works_on(doctor, on):
        earliest = (now + timedelta(hours=BOOKING_LEAD_HOURS)).strftime("%H:%M")
        result["earliest_bookable_today"] = earliest
        result["lead_time_note"] = (
            f"Bookings need at least {BOOKING_LEAD_HOURS}h notice, so the earliest time "
            f"bookable today is {earliest}. If the patient asks for an earlier time today, "
            "tell them it's too soon to book (not that it's unavailable) and offer the "
            "listed times or another day."
        )
    return result


def _resolve_slot(args: dict, ctx: AgentContext):
    """Shared validation for book/reschedule -> (doctor, service, start, end) or error dict."""
    doctor = find_doctor(args.get("doctor", ""), ctx.doctors)
    if not doctor:
        return {"error": "doctor_not_found"}
    service = find_service(args.get("service", ""), ctx.services)
    if not service:
        return {"error": "service_not_found"}
    on = parse_date(args.get("date", ""), _now().date())
    clock = parse_clock(args.get("time", ""))
    if not on or not clock:
        return {"error": "bad_datetime", "hint": "Need a valid date and time."}
    start = datetime.combine(on, clock, tzinfo=TZ)
    end = start + timedelta(minutes=service["duration_min"])
    return doctor, service, start, end


def _book_appointment(args: dict, ctx: AgentContext) -> dict:
    resolved = _resolve_slot(args, ctx)
    if isinstance(resolved, dict):
        return resolved
    doctor, service, start, end = resolved

    day_start, day_end = day_bounds(start.date())
    booked = db.booked_intervals(ctx.tenant_id, doctor["name"], day_start, day_end)
    valid = available_slots(doctor, start.date(), service["duration_min"], booked, _now())
    if start not in valid:
        return {"error": "slot_unavailable",
                "available_times": [s.strftime("%H:%M") for s in valid[:12]]}

    # Clinic-specific intake fields (device code, insurance, payment method, ...).
    extra = args.get("extra") if isinstance(args.get("extra"), dict) else {}
    field_error = check_booking_fields(ctx.clinic_data, extra)
    if field_error:
        return field_error

    name = (args.get("patient_name") or "").strip() or db.get_patient_name(ctx.tenant_id, ctx.wa_user)
    phone = (args.get("phone") or "").strip() or ctx.wa_user
    row = db.create_appointment(ctx.tenant_id, ctx.wa_user, name, phone, doctor["name"],
                                service["name"], start, end, extra=extra or None)
    if row.get("conflict"):
        booked = db.booked_intervals(ctx.tenant_id, doctor["name"], day_start, day_end)
        valid = available_slots(doctor, start.date(), service["duration_min"], booked, _now())
        return {"error": "just_taken",
                "available_times": [s.strftime("%H:%M") for s in valid[:12]]}

    db.upsert_patient(ctx.tenant_id, ctx.wa_user, name)
    _snapshot_risk(ctx, row)
    ctx.booked_ids.append(row["id"])
    ctx.actions.append(f"booked #{row['id']} {doctor['name']} {_fmt(start)} ({name}, {phone})")
    return {"booked": True, "appointment_id": row["id"], "patient_name": name, "phone": phone,
            "doctor": doctor["name"], "service": service["name"], "when": _fmt(start),
            "details": extra or None}


def _snapshot_risk(ctx: AgentContext, appt_row: dict) -> None:
    """Record a no-show risk snapshot on a freshly booked/rescheduled appointment.
    Best-effort — never blocks the booking if scoring fails."""
    try:
        from app.no_show import risk_for_appointment
        stats = db.patient_history_stats(ctx.tenant_id, ctx.wa_user, appt_row["id"])
        score, band = risk_for_appointment(appt_row, stats)
        db.set_appointment_risk(ctx.tenant_id, appt_row["id"], score, band)
    except Exception:  # noqa: BLE001
        log.warning("risk snapshot failed for appt %s", appt_row.get("id"))


def _get_faqs(args: dict, ctx: AgentContext) -> dict:
    data = ctx.clinic_data or {}
    return {"faqs": data.get("faqs", []),
            "policy": data.get("appointment_policy", {})}


def _get_my_appointments(args: dict, ctx: AgentContext) -> dict:
    rows = db.upcoming_appointments(ctx.tenant_id, ctx.wa_user, _now())
    return {"appointments": [
        {"appointment_id": r["id"], "doctor": r["doctor"], "service": r["service"],
         "when": _fmt(r["start_at"]), "status": r["status"]} for r in rows]}


def _owned(appointment_id: int, ctx: AgentContext) -> dict | None:
    appt = db.get_appointment(ctx.tenant_id, appointment_id)
    if not appt or appt["wa_user"] != ctx.wa_user:
        return None
    return appt


def _reschedule_appointment(args: dict, ctx: AgentContext) -> dict:
    appt = _owned(int(args["appointment_id"]), ctx)
    if not appt:
        return {"error": "appointment_not_found"}
    # A no-show can be rescheduled too — that's the whole point of recovery outreach.
    if appt["status"] not in ("confirmed", "no_show"):
        return {"error": "not_active", "status": appt["status"]}

    on = parse_date(args.get("date", ""), _now().date())
    clock = parse_clock(args.get("time", ""))
    if not on or not clock:
        return {"error": "bad_datetime"}
    start = datetime.combine(on, clock, tzinfo=TZ)
    duration = (appt["end_at"] - appt["start_at"])
    end = start + duration

    doctor = find_doctor(appt["doctor"], ctx.doctors)
    day_start, day_end = day_bounds(start.date())
    booked = db.booked_intervals(ctx.tenant_id, appt["doctor"], day_start, day_end)
    valid = available_slots(doctor, start.date(), int(duration.total_seconds() // 60), booked, _now())
    if start not in valid:
        return {"error": "slot_unavailable",
                "available_times": [s.strftime("%H:%M") for s in valid[:12]]}

    row = db.reschedule(ctx.tenant_id, appt["id"], start, end)
    if row.get("conflict"):
        return {"error": "just_taken"}
    # Rescheduling closes any open no-show recovery, and the new slot gets a fresh score.
    db.resolve_followup_for_appointment(ctx.tenant_id, appt["id"], "reschedule")
    _snapshot_risk(ctx, row)
    ctx.changed_ids.append(appt["id"])
    ctx.actions.append(f"rescheduled #{appt['id']} -> {_fmt(start)}")
    return {"rescheduled": True, "appointment_id": appt["id"], "when": _fmt(start)}


def _cancel_appointment(args: dict, ctx: AgentContext) -> dict:
    appt = _owned(int(args["appointment_id"]), ctx)
    if not appt:
        return {"error": "appointment_not_found"}
    if appt["status"] == "cancelled":
        return {"already_cancelled": True}
    db.set_appointment_status(ctx.tenant_id, appt["id"], "cancelled")
    db.resolve_followup_for_appointment(ctx.tenant_id, appt["id"], "cancel")
    ctx.changed_ids.append(appt["id"])
    ctx.actions.append(f"cancelled #{appt['id']}")
    return {"cancelled": True, "appointment_id": appt["id"]}


def _escalate_to_human(args: dict, ctx: AgentContext) -> dict:
    ctx.needs_human = True
    ctx.emergency = bool(args.get("emergency"))
    ctx.escalation_reason = (args.get("reason") or "").strip() or "unspecified"
    ctx.actions.append(f"escalated ({'EMERGENCY' if ctx.emergency else 'handover'}): {ctx.escalation_reason}")
    return {"escalated": True}


_REASON_KEYWORDS = {
    "forgot": "forgot", "forget": "forgot", "slip": "forgot",
    "busy": "busy", "work": "busy", "time": "busy",
    "emergency": "emergency", "sick": "emergency", "urgent": "emergency",
    "price": "price", "cost": "price", "expensive": "price", "money": "price",
    "another clinic": "other_clinic", "other clinic": "other_clinic",
    "different clinic": "other_clinic", "switched": "other_clinic", "elsewhere": "other_clinic",
}


def _normalize_reason(value) -> str | None:
    from app.no_show import REASONS
    if not value:
        return None
    v = str(value).strip().lower()
    if v in REASONS:
        return v
    for kw, reason in _REASON_KEYWORDS.items():
        if kw in v:
            return reason
    return "other"


def _record_no_show_response(args: dict, ctx: AgentContext) -> dict:
    appt_id = args.get("appointment_id")
    try:
        appt_id = int(appt_id)
    except (TypeError, ValueError):
        appt_id = (ctx.no_show or {}).get("appointment_id")
    # Only the patient's own missed appointment can be annotated. Fall back to the
    # open follow-up if the model passed an id this patient doesn't own.
    if not appt_id or not _owned(int(appt_id), ctx):
        appt_id = (ctx.no_show or {}).get("appointment_id")
    if not appt_id:
        return {"error": "no_open_no_show"}
    outcome = (args.get("outcome") or "").strip().lower() or None
    if outcome not in ("reschedule", "call", "cancel"):
        outcome = None
    reason = _normalize_reason(args.get("reason"))
    ok = db.record_no_show_response(ctx.tenant_id, int(appt_id), outcome=outcome, reason=reason)
    ctx.actions.append(f"no-show response #{appt_id}: outcome={outcome}, reason={reason}")
    return {"recorded": ok, "appointment_id": int(appt_id), "outcome": outcome, "reason": reason}


def _record_review(args: dict, ctx: AgentContext) -> dict:
    appt_id = args.get("appointment_id")
    try:
        appt_id = int(appt_id)
    except (TypeError, ValueError):
        appt_id = (ctx.review or {}).get("appointment_id")
    if not appt_id or not _owned(int(appt_id), ctx):
        appt_id = (ctx.review or {}).get("appointment_id")
    if not appt_id:
        return {"error": "no_open_review"}
    try:
        rating = int(args.get("rating"))
    except (TypeError, ValueError):
        return {"error": "bad_rating", "hint": "Rating must be an integer 1-5."}
    if not 1 <= rating <= 5:
        return {"error": "bad_rating", "hint": "Rating must be 1-5."}
    comment = (args.get("comment") or "").strip() or None
    ok = db.record_review(ctx.tenant_id, int(appt_id), rating, comment)
    ctx.actions.append(f"review #{appt_id}: {rating}★")
    return {"recorded": ok, "appointment_id": int(appt_id), "rating": rating}


_HANDLERS = {
    "list_services": _list_services,
    "list_doctors": _list_doctors,
    "check_availability": _check_availability,
    "book_appointment": _book_appointment,
    "get_faqs": _get_faqs,
    "get_my_appointments": _get_my_appointments,
    "reschedule_appointment": _reschedule_appointment,
    "cancel_appointment": _cancel_appointment,
    "escalate_to_human": _escalate_to_human,
    "record_no_show_response": _record_no_show_response,
    "record_review": _record_review,
}


def dispatch(name: str, args: dict, ctx: AgentContext) -> dict:
    handler = _HANDLERS.get(name)
    if not handler:
        return {"error": f"unknown_tool:{name}"}
    try:
        result = handler(args or {}, ctx)
        log.info("[tool] %s(%s) -> %s", name, args, result)
        return result
    except Exception as e:  # noqa: BLE001
        log.exception("Tool %s failed", name)
        from app import incidents
        incidents.record("tool", f"Tool '{name}' failed", detail=f"{args} -> {e}",
                         tenant_id=ctx.tenant_id, wa_user=ctx.wa_user)
        return {"error": "tool_failed", "detail": str(e)}
