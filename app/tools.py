"""Agent tools: JSON-schema specs the model sees + Python handlers that run them.

Handlers take (args: dict, ctx: AgentContext) and return a JSON-serialisable dict that
is fed back to the model. Side effects (bookings, escalations) are recorded on ctx so the
webhook can act on them (notify staff, log intent) after the turn completes.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app import db
from app.config import TZ
from app.llm import ToolSpec
from app.scheduling import (
    available_slots,
    day_bounds,
    find_doctor,
    find_service,
    parse_clock,
    parse_date,
)

log = logging.getLogger(__name__)

DEFAULT_DURATION_MIN = 30


@dataclass
class AgentContext:
    wa_user: str
    reply: str = ""
    needs_human: bool = False
    emergency: bool = False
    escalation_reason: str | None = None
    booked_ids: list[int] = field(default_factory=list)
    changed_ids: list[int] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)

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
             "Reserve a specific slot. Only use a time confirmed free by check_availability.",
             {"type": "object", "properties": {
                 "patient_name": {"type": "string"},
                 "doctor": {"type": "string"},
                 "service": {"type": "string"},
                 "date": {"type": "string", "description": "YYYY-MM-DD or 'today'/'tomorrow'."},
                 "time": {"type": "string", "description": "Start time, e.g. '17:00' or '5:00 PM'."}},
              "required": ["patient_name", "doctor", "service", "date", "time"]}),
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
]


# --- Handlers ---

def _list_services(args: dict, ctx: AgentContext) -> dict:
    from app.scheduling import SERVICES
    return {"services": [
        {"name": s["name"], "price_sar": s["price_sar"], "duration_min": s["duration_min"]}
        for s in SERVICES]}


def _list_doctors(args: dict, ctx: AgentContext) -> dict:
    from app.scheduling import DOCTORS
    spec = (args.get("specialty") or "").lower().strip()
    docs = DOCTORS
    if spec:
        docs = [d for d in DOCTORS if spec in d["specialty"].lower()] or DOCTORS
    return {"doctors": [
        {"name": d["name"], "specialty": d["specialty"],
         "available_days": d["available_days"], "available_hours": d["available_hours"]}
        for d in docs]}


def _check_availability(args: dict, ctx: AgentContext) -> dict:
    from app.scheduling import DOCTORS
    doctor = find_doctor(args.get("doctor", ""))
    if not doctor:
        return {"error": "doctor_not_found",
                "available_doctors": [d["name"] for d in DOCTORS]}
    on = parse_date(args.get("date", ""), _now().date())
    if not on:
        return {"error": "bad_date", "hint": "Use YYYY-MM-DD or 'today'/'tomorrow'."}
    service = find_service(args.get("service", "")) if args.get("service") else None
    duration = service["duration_min"] if service else DEFAULT_DURATION_MIN

    start, end = day_bounds(on)
    booked = db.booked_intervals(doctor["name"], start, end)
    slots = available_slots(doctor, on, duration, booked, _now())
    return {
        "doctor": doctor["name"],
        "date": on.isoformat(),
        "service": service["name"] if service else None,
        "slot_duration_min": duration,
        "available_times": [s.strftime("%H:%M") for s in slots[:12]],
        "more_available": len(slots) > 12,
        "note": None if slots else "No free slots that day — suggest another day.",
    }


def _resolve_slot(args: dict):
    """Shared validation for book/reschedule -> (doctor, service, start, end) or error dict."""
    doctor = find_doctor(args.get("doctor", ""))
    if not doctor:
        return {"error": "doctor_not_found"}
    service = find_service(args.get("service", ""))
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
    resolved = _resolve_slot(args)
    if isinstance(resolved, dict):
        return resolved
    doctor, service, start, end = resolved

    day_start, day_end = day_bounds(start.date())
    booked = db.booked_intervals(doctor["name"], day_start, day_end)
    valid = available_slots(doctor, start.date(), service["duration_min"], booked, _now())
    if start not in valid:
        return {"error": "slot_unavailable",
                "available_times": [s.strftime("%H:%M") for s in valid[:12]]}

    name = (args.get("patient_name") or "").strip() or db.get_patient_name(ctx.wa_user)
    row = db.create_appointment(ctx.wa_user, name, doctor["name"], service["name"], start, end)
    if row.get("conflict"):
        booked = db.booked_intervals(doctor["name"], day_start, day_end)
        valid = available_slots(doctor, start.date(), service["duration_min"], booked, _now())
        return {"error": "just_taken",
                "available_times": [s.strftime("%H:%M") for s in valid[:12]]}

    db.upsert_patient(ctx.wa_user, name)
    ctx.booked_ids.append(row["id"])
    ctx.actions.append(f"booked #{row['id']} {doctor['name']} {_fmt(start)}")
    return {"booked": True, "appointment_id": row["id"], "patient_name": name,
            "doctor": doctor["name"], "service": service["name"], "when": _fmt(start)}


def _get_my_appointments(args: dict, ctx: AgentContext) -> dict:
    rows = db.upcoming_appointments(ctx.wa_user, _now())
    return {"appointments": [
        {"appointment_id": r["id"], "doctor": r["doctor"], "service": r["service"],
         "when": _fmt(r["start_at"]), "status": r["status"]} for r in rows]}


def _owned(appointment_id: int, ctx: AgentContext) -> dict | None:
    appt = db.get_appointment(appointment_id)
    if not appt or appt["wa_user"] != ctx.wa_user:
        return None
    return appt


def _reschedule_appointment(args: dict, ctx: AgentContext) -> dict:
    appt = _owned(int(args["appointment_id"]), ctx)
    if not appt:
        return {"error": "appointment_not_found"}
    if appt["status"] != "confirmed":
        return {"error": "not_active", "status": appt["status"]}

    on = parse_date(args.get("date", ""), _now().date())
    clock = parse_clock(args.get("time", ""))
    if not on or not clock:
        return {"error": "bad_datetime"}
    start = datetime.combine(on, clock, tzinfo=TZ)
    duration = (appt["end_at"] - appt["start_at"])
    end = start + duration

    doctor = find_doctor(appt["doctor"])
    day_start, day_end = day_bounds(start.date())
    booked = db.booked_intervals(appt["doctor"], day_start, day_end)
    valid = available_slots(doctor, start.date(), int(duration.total_seconds() // 60), booked, _now())
    if start not in valid:
        return {"error": "slot_unavailable",
                "available_times": [s.strftime("%H:%M") for s in valid[:12]]}

    row = db.reschedule(appt["id"], start, end)
    if row.get("conflict"):
        return {"error": "just_taken"}
    ctx.changed_ids.append(appt["id"])
    ctx.actions.append(f"rescheduled #{appt['id']} -> {_fmt(start)}")
    return {"rescheduled": True, "appointment_id": appt["id"], "when": _fmt(start)}


def _cancel_appointment(args: dict, ctx: AgentContext) -> dict:
    appt = _owned(int(args["appointment_id"]), ctx)
    if not appt:
        return {"error": "appointment_not_found"}
    if appt["status"] == "cancelled":
        return {"already_cancelled": True}
    db.set_appointment_status(appt["id"], "cancelled")
    ctx.changed_ids.append(appt["id"])
    ctx.actions.append(f"cancelled #{appt['id']}")
    return {"cancelled": True, "appointment_id": appt["id"]}


def _escalate_to_human(args: dict, ctx: AgentContext) -> dict:
    ctx.needs_human = True
    ctx.emergency = bool(args.get("emergency"))
    ctx.escalation_reason = (args.get("reason") or "").strip() or "unspecified"
    ctx.actions.append(f"escalated ({'EMERGENCY' if ctx.emergency else 'handover'}): {ctx.escalation_reason}")
    return {"escalated": True}


_HANDLERS = {
    "list_services": _list_services,
    "list_doctors": _list_doctors,
    "check_availability": _check_availability,
    "book_appointment": _book_appointment,
    "get_my_appointments": _get_my_appointments,
    "reschedule_appointment": _reschedule_appointment,
    "cancel_appointment": _cancel_appointment,
    "escalate_to_human": _escalate_to_human,
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
        return {"error": "tool_failed", "detail": str(e)}
