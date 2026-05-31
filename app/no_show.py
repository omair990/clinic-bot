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
window require a pre-approved message template. Set NO_SHOW_USE_TEMPLATES=true and register
the templates (see config.py) to send via templates; otherwise these go as free-form text,
which only delivers inside the 24h window.
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
    NO_SHOW_TEMPLATE_LANG,
    PRE_APPT_CONFIRM_ENABLED,
    PRE_APPT_CONFIRM_LEAD_HOURS,
    NO_SHOW_USE_TEMPLATES,
    TZ,
    WA_TEMPLATE_FOLLOWUP,
    WA_TEMPLATE_NO_SHOW,
    WA_TEMPLATE_REMINDER,
)
from app.events import publish
from app.wa_client import send_template, send_text

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
        f"Reminder: you have {_subject(service, doctor)} on {when}. Will you be able to "
        "attend? Please reply 1 to confirm, 2 to reschedule, or 3 to cancel. See you then!"
    )


# --- Orchestration ---

def _now() -> datetime:
    return datetime.now(TZ)


def _creds(tenant: dict) -> dict:
    return {"phone_number_id": tenant.get("wa_phone_number_id"),
            "access_token": tenant.get("wa_access_token")}


# Fallback template names from env, by message kind.
_ENV_TEMPLATES = {"no_show": WA_TEMPLATE_NO_SHOW, "followup": WA_TEMPLATE_FOLLOWUP,
                  "reminder": WA_TEMPLATE_REMINDER}


def resolve_template(kind: str, tenant: dict | None) -> dict | None:
    """The approved template to use for this message kind, or None to send free text.

    Templates are only used when NO_SHOW_USE_TEMPLATES is on AND a name is configured —
    per-tenant via clinic_data.no_show_templates, else the platform env default. This
    lets a clinic adopt templates without forcing every clinic to.
    """
    if not NO_SHOW_USE_TEMPLATES:
        return None
    cfg = ((tenant or {}).get("clinic_data") or {}).get("no_show_templates") or {}
    name = cfg.get(kind) or _ENV_TEMPLATES.get(kind)
    if not name:
        return None
    return {"name": name, "language": cfg.get("language") or NO_SHOW_TEMPLATE_LANG}


async def _send_and_log(to: str, body: str, creds: dict, tenant_id: int, *,
                        template: dict | None = None, params: list | None = None) -> None:
    """Send a proactive message and mirror it into the conversation log + live feed,
    so it shows up in the dashboard and the agent has it in history on the reply.

    Sends via an approved template when one is given (needed outside the 24h window),
    otherwise free-form text. Either way we log the human-readable `body` so the
    dashboard and the agent's history stay readable."""
    if template:
        await send_template(to, template["name"], template["language"], params, **creds)
    else:
        await send_text(to, body, **creds)
    await asyncio.to_thread(db.log_message, tenant_id, to, "out", body, NO_SHOW_INTENT, False)
    publish("message", {"wa_user": to, "direction": "out", "text": body,
                        "intent": NO_SHOW_INTENT, "tenant_id": tenant_id})
    log.info("no-show out %s (%s): %s", to, "template" if template else "text", body[:80])


async def send_no_show_notification(*, to: str, service: str | None, doctor: str | None,
                                    creds: dict, tenant_id: int, followup_id: int,
                                    tenant: dict | None = None, advance: bool = True) -> None:
    """Send the initial recovery message. Used by both the sweep (auto-send) and the
    dashboard's manual 'Send'/'Resend'. `advance=True` moves the follow-up to 'notified'."""
    template = resolve_template("no_show", tenant)
    await _send_and_log(to, no_show_message(service, doctor), creds, tenant_id,
                        template=template, params=[_subject(service, doctor)])
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
                    creds=_creds(tenant), tenant_id=tid, followup_id=fu["id"], tenant=tenant)
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
                                _creds(tenant), f["tenant_id"],
                                template=resolve_template("followup", tenant),
                                params=[_subject(f["service"], f["doctor"])])
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


async def _score_upcoming(now: datetime) -> int:
    """Give every unscored upcoming appointment a no-show risk snapshot (for the dashboard
    and analytics). Sends nothing."""
    unscored = await asyncio.to_thread(db.unscored_upcoming_appointments, now)
    for a in unscored:
        stats = await asyncio.to_thread(db.patient_history_stats, a["tenant_id"],
                                        a["wa_user"], a["id"])
        score, band = risk_for_appointment(a, stats)
        await asyncio.to_thread(db.set_appointment_risk, a["tenant_id"], a["id"], score, band)
    return len(unscored)


async def _send_confirmations(now: datetime, tenants: dict[int, dict]) -> int:
    """Ask EVERY upcoming patient to confirm/reschedule/cancel before their appointment —
    the universal pre-appointment 'will you attend?' nudge (once per appointment)."""
    until = now + timedelta(hours=PRE_APPT_CONFIRM_LEAD_HOURS)
    due = await asyncio.to_thread(db.upcoming_reminders_due, now, until)
    sent = 0
    for a in due:
        tenant = tenants.get(a["tenant_id"])
        if not tenant:
            continue
        when = a["start_at"].astimezone(TZ).strftime("%A %d %B, %I:%M %p")
        try:
            await _send_and_log(a["wa_user"], reminder_message(a["service"], a["doctor"], when),
                                _creds(tenant), a["tenant_id"],
                                template=resolve_template("reminder", tenant),
                                params=[_subject(a["service"], a["doctor"]), when])
            await asyncio.to_thread(db.mark_reminded, a["tenant_id"], a["id"])
            sent += 1
        except Exception as ex:  # noqa: BLE001
            log.exception("pre-appointment confirmation failed for %s", a["wa_user"])
            incidents.record("whatsapp", "Pre-appointment confirmation failed", detail=repr(ex),
                             tenant_id=a["tenant_id"], wa_user=a["wa_user"])
    return sent


async def sweep() -> None:
    """One pass: detect no-shows, send day-later follow-ups, retire silent leads, and
    (premium) score upcoming appointments + remind high-risk patients."""
    now = _now()
    tenants = {t["id"]: t for t in await asyncio.to_thread(db.all_active_tenants)}

    detected = await _detect_no_shows(now, tenants)
    followed = await _send_followups(now, tenants)
    inactive = await _mark_inactive(now)
    scored = await _score_upcoming(now) if NO_SHOW_PREDICTOR else 0
    confirmed = await _send_confirmations(now, tenants) if PRE_APPT_CONFIRM_ENABLED else 0

    if detected or followed or inactive or confirmed:
        log.info("no-show sweep: %s detected, %s followed-up, %s inactive, "
                 "%s scored, %s pre-appointment confirmations", detected, followed, inactive,
                 scored, confirmed)
