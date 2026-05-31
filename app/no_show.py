"""No-show recovery & risk prediction.

Two responsibilities:

1. **Recovery** — when an appointment's time passes with the patient still only
   "confirmed" (never checked in), treat it as a no-show: flip the status, open a
   follow-up record, and reach out over WhatsApp offering to reschedule / request a
   call / cancel. A day later, nudge again; another day of silence marks the lead
   inactive. The patient's reply is handled by the normal agent loop (see prompts.py
   and tools.py), which records the outcome and the reason they missed.

2. **Prediction (premium)** — score every upcoming appointment for no-show risk from
   the patient's history, and give high-risk patients an extra reminder before their
   visit. `compute_risk` is a pure, explainable rule — easy to test and audit.

The detection sweep is driven by a background loop in main.py. `compute_risk` has no
I/O so it's unit-tested directly; everything else is thin orchestration over db.py.

NOTE: proactive (business-initiated) WhatsApp messages outside the 24-hour customer-care
window require a pre-approved message template. This module sends free-form text like the
rest of the app; in production, wire these to approved templates.
"""
import asyncio
import logging
from datetime import datetime, timedelta

from app import db, incidents
from app.config import (
    NO_SHOW_AUTO_SEND,
    NO_SHOW_FOLLOWUP_HOURS,
    NO_SHOW_GRACE_MINUTES,
    NO_SHOW_INACTIVE_HOURS,
    NO_SHOW_PREDICTOR,
    NO_SHOW_RISK_REMINDER_LEAD_HOURS,
    TZ,
)
from app.events import publish
from app.wa_client import send_text

log = logging.getLogger(__name__)

NO_SHOW_INTENT = "no_show"

# Canonical "why did you miss?" reasons surfaced on the dashboard. The agent maps the
# patient's free text onto one of these via the record_no_show_response tool.
REASONS = ("forgot", "busy", "emergency", "price", "other_clinic", "other")
REASON_LABELS = {
    "forgot": "Forgot", "busy": "Busy", "emergency": "Emergency",
    "price": "Price concern", "other_clinic": "Chose another clinic", "other": "Other",
}


# --- Risk scoring (pure) ---

def compute_risk(stats: dict) -> tuple[int, str]:
    """Rule-based no-show risk from a patient's history. Returns (score 0-100, band).

    stats keys (all optional): no_shows, cancellations, completed (prior counts),
    lead_hours (booking lead time), hour (appointment hour of day, 0-23).
    Bands: low < 30, medium 30-65, high > 65.
    """
    no_shows = int(stats.get("no_shows") or 0)
    cancellations = int(stats.get("cancellations") or 0)
    completed = int(stats.get("completed") or 0)
    lead_hours = stats.get("lead_hours")
    hour = stats.get("hour")
    is_new = (no_shows + cancellations + completed) == 0

    score = 15                               # baseline for any booking
    score += min(no_shows * 25, 50)          # the strongest signal
    score += min(cancellations * 8, 24)
    score -= min(completed * 6, 30)          # a track record of showing up lowers risk
    if is_new:
        score += 10                          # unknown patient = some uncertainty
    if lead_hours is not None:
        if lead_hours < 4:
            score += 10                      # booked last-minute
        elif lead_hours > 14 * 24:
            score += 8                       # booked far out — easy to forget
    if hour is not None:
        if hour >= 18:
            score += 6                       # busy evening slots
        elif hour < 10:
            score += 4                       # early mornings

    score = max(0, min(100, score))
    band = "high" if score > 65 else "medium" if score >= 30 else "low"
    return score, band


def risk_for_appointment(appt: dict, stats: dict) -> tuple[int, str]:
    """Risk for a specific appointment row, deriving lead time and hour from it."""
    lead_hours = None
    if appt.get("created_at") and appt.get("start_at"):
        lead_hours = (appt["start_at"] - appt["created_at"]).total_seconds() / 3600
    hour = appt["start_at"].astimezone(TZ).hour if appt.get("start_at") else None
    return compute_risk({**stats, "lead_hours": lead_hours, "hour": hour})


# --- Message copy ---

def _subject(service: str | None, doctor: str | None) -> str:
    if service and doctor:
        return f"{service} with {doctor}"
    return "your appointment"


def no_show_message(service: str | None, doctor: str | None) -> str:
    return (
        f"Hi, we noticed you missed {_subject(service, doctor)} today and we hope "
        "everything's okay. Would you like to:\n"
        "1️⃣ Reschedule\n"
        "2️⃣ Request a call\n"
        "3️⃣ Cancel treatment\n\n"
        "Just reply 1, 2 or 3 — and if you don't mind sharing, what made you miss it?"
    )


def followup_message(service: str | None, doctor: str | None) -> str:
    return (
        f"Just following up about {_subject(service, doctor)} that you missed. "
        "We'd love to help — reply 1 to see available times, 2 for a call back, "
        "or 3 to cancel. We're here whenever you're ready."
    )


def reminder_message(service: str | None, doctor: str | None, when: str) -> str:
    return (
        f"Friendly reminder: you have {_subject(service, doctor)} on {when}. "
        "Please reply 1 to confirm, 2 to reschedule, or 3 to cancel. See you then!"
    )


# --- Orchestration ---

def _now() -> datetime:
    return datetime.now(TZ)


def _creds(tenant: dict) -> dict:
    return {"phone_number_id": tenant.get("wa_phone_number_id"),
            "access_token": tenant.get("wa_access_token")}


async def _send_and_log(to: str, body: str, creds: dict, tenant_id: int) -> None:
    """Send a proactive message and mirror it into the conversation log + live feed,
    so it shows up in the dashboard and the agent has it in history on the reply."""
    await send_text(to, body, **creds)
    await asyncio.to_thread(db.log_message, tenant_id, to, "out", body, NO_SHOW_INTENT, False)
    publish("message", {"wa_user": to, "direction": "out", "text": body,
                        "intent": NO_SHOW_INTENT, "tenant_id": tenant_id})
    log.info("no-show out %s: %s", to, body[:80])


async def send_no_show_notification(*, to: str, service: str | None, doctor: str | None,
                                    creds: dict, tenant_id: int, followup_id: int,
                                    advance: bool = True) -> None:
    """Send the initial recovery message. Used by both the sweep (auto-send) and the
    dashboard's manual 'Send'/'Resend'. `advance=True` moves the follow-up to 'notified'."""
    await _send_and_log(to, no_show_message(service, doctor), creds, tenant_id)
    if advance:
        await asyncio.to_thread(db.set_followup_stage, followup_id, "notified",
                                stamp="notified_at")


async def _detect_no_shows(now: datetime, tenants: dict[int, dict]) -> int:
    cutoff = now - timedelta(minutes=NO_SHOW_GRACE_MINUTES)
    appts = await asyncio.to_thread(db.find_no_shows, cutoff)
    count = 0
    for a in appts:
        tid = a["tenant_id"]
        score, band = a.get("risk_score"), a.get("risk_band")
        if score is None:
            stats = await asyncio.to_thread(db.patient_history_stats, tid, a["wa_user"], a["id"])
            score, band = risk_for_appointment(a, stats)
        fu = await asyncio.to_thread(db.mark_no_show, tid, a["id"], a["wa_user"], score, band)
        if not fu:
            continue  # raced with another sweep
        count += 1
        tenant = tenants.get(tid)
        if NO_SHOW_AUTO_SEND and tenant:
            try:
                await send_no_show_notification(
                    to=a["wa_user"], service=a["service"], doctor=a["doctor"],
                    creds=_creds(tenant), tenant_id=tid, followup_id=fu["id"])
            except Exception as ex:  # noqa: BLE001 — one failure mustn't stop the sweep
                log.exception("no-show notify failed for %s", a["wa_user"])
                incidents.record("whatsapp", "No-show notification failed",
                                 detail=repr(ex), tenant_id=tid, wa_user=a["wa_user"])
    return count


async def _send_followups(now: datetime, tenants: dict[int, dict]) -> int:
    cutoff = now - timedelta(hours=NO_SHOW_FOLLOWUP_HOURS)
    due = await asyncio.to_thread(db.followups_due_followup, cutoff)
    count = 0
    for f in due:
        tenant = tenants.get(f["tenant_id"])
        if not tenant:
            continue
        try:
            await _send_and_log(f["wa_user"], followup_message(f["service"], f["doctor"]),
                                _creds(tenant), f["tenant_id"])
            await asyncio.to_thread(db.set_followup_stage, f["id"], "followed_up",
                                    stamp="followup_at")
            count += 1
        except Exception as ex:  # noqa: BLE001
            log.exception("no-show follow-up failed for %s", f["wa_user"])
            incidents.record("whatsapp", "No-show follow-up failed", detail=repr(ex),
                             tenant_id=f["tenant_id"], wa_user=f["wa_user"])
    return count


async def _mark_inactive(now: datetime) -> int:
    cutoff = now - timedelta(hours=NO_SHOW_INACTIVE_HOURS)
    due = await asyncio.to_thread(db.followups_due_inactive, cutoff)
    for f in due:
        await asyncio.to_thread(db.set_followup_stage, f["id"], "inactive", stamp="resolved_at")
    return len(due)


async def _score_and_remind(now: datetime, tenants: dict[int, dict]) -> tuple[int, int]:
    # 1) Score any upcoming appointment that doesn't have a risk snapshot yet.
    unscored = await asyncio.to_thread(db.unscored_upcoming_appointments, now)
    for a in unscored:
        stats = await asyncio.to_thread(db.patient_history_stats, a["tenant_id"],
                                        a["wa_user"], a["id"])
        score, band = risk_for_appointment(a, stats)
        await asyncio.to_thread(db.set_appointment_risk, a["tenant_id"], a["id"], score, band)

    # 2) Give high-risk patients an extra reminder shortly before their appointment.
    until = now + timedelta(hours=NO_SHOW_RISK_REMINDER_LEAD_HOURS)
    due = await asyncio.to_thread(db.high_risk_reminders_due, now, until)
    reminded = 0
    for a in due:
        tenant = tenants.get(a["tenant_id"])
        if not tenant:
            continue
        when = a["start_at"].astimezone(TZ).strftime("%A %d %B, %I:%M %p")
        try:
            await _send_and_log(a["wa_user"], reminder_message(a["service"], a["doctor"], when),
                                _creds(tenant), a["tenant_id"])
            await asyncio.to_thread(db.mark_reminded, a["tenant_id"], a["id"])
            reminded += 1
        except Exception as ex:  # noqa: BLE001
            log.exception("high-risk reminder failed for %s", a["wa_user"])
            incidents.record("whatsapp", "High-risk reminder failed", detail=repr(ex),
                             tenant_id=a["tenant_id"], wa_user=a["wa_user"])
    return len(unscored), reminded


async def sweep() -> None:
    """One pass: detect no-shows, send day-later follow-ups, retire silent leads, and
    (premium) score upcoming appointments + remind high-risk patients."""
    now = _now()
    tenants = {t["id"]: t for t in await asyncio.to_thread(db.all_active_tenants)}

    detected = await _detect_no_shows(now, tenants)
    followed = await _send_followups(now, tenants)
    inactive = await _mark_inactive(now)
    scored = reminded = 0
    if NO_SHOW_PREDICTOR:
        scored, reminded = await _score_and_remind(now, tenants)

    if detected or followed or inactive or reminded:
        log.info("no-show sweep: %s detected, %s followed-up, %s inactive, "
                 "%s scored, %s high-risk reminders", detected, followed, inactive,
                 scored, reminded)
