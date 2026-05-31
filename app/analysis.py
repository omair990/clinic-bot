"""AI conversation analysis: a receptionist-style summary + a Hot/Warm/Cold lead score.

Phases 2 (Conversation Summary) and 3 (Lead Scoring) of the AI roadmap are produced by a
SINGLE LLM call over the conversation thread — they need the same context, so doing both at
once halves the cost. The result is cached in `conversation_analysis` and rebuilt only when
the message count changes (so opening a conversation doesn't re-spend tokens every time).

Resilience: if every LLM provider is down (e.g. exhausted credits), we fall back to a
deterministic heuristic so the dashboard always shows a sensible lead band — the row records
whether it came from the model ('ai') or the fallback ('heuristic').
"""
import json
import logging
from datetime import datetime

from app import db
from app.config import TZ
from app.llm import LLMUnavailable, Msg, generate

log = logging.getLogger(__name__)

URGENCY = ("low", "medium", "high")
SENTIMENT = ("positive", "neutral", "negative")
LEAD_BANDS = ("hot", "warm", "cold")

_SYSTEM = """You analyze a clinic's WhatsApp conversation for the front-desk team.
Return ONLY a single JSON object (no prose, no code fence) with EXACTLY these keys:
{
  "customer_name": string|null,
  "requested_service": string|null,
  "appointment_preference": string|null,   // preferred day/time/doctor if mentioned
  "insurance": string|null,                 // insurance provider if mentioned (e.g. Bupa)
  "urgency": "low"|"medium"|"high",
  "sentiment": "positive"|"neutral"|"negative",
  "next_action": string,                    // the single best next step for staff
  "lead_band": "hot"|"warm"|"cold",
  "lead_score": integer 0-100,
  "lead_rationale": string                  // one short sentence
}
Lead scoring — judge booking likelihood from intent, engagement and urgency:
hot = clear intent to book / urgent / already chose a slot; warm = interested, comparing or
asking details; cold = vague, just browsing, or unresponsive. Keep every string short.
Use the patient's own language only inside string values; keep the JSON keys/enums English."""


def _extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of a model reply (tolerates code fences/prose)."""
    if not text:
        return None
    i, j = text.find("{"), text.rfind("}")
    if i == -1 or j == -1 or j < i:
        return None
    try:
        obj = json.loads(text[i:j + 1])
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


def _transcript(thread: list[dict], limit: int = 24) -> str:
    lines = []
    for m in thread[-limit:]:
        who = "Patient" if m["direction"] == "in" else "Assistant"
        text = (m.get("message") or "").strip().replace("\n", " ")
        if text:
            lines.append(f"{who}: {text}")
    return "\n".join(lines)


def _clamp_score(value) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return 0


def _band_for_score(score: int) -> str:
    return "hot" if score >= 70 else "warm" if score >= 40 else "cold"


def heuristic_analysis(thread: list[dict], patient_name: str | None,
                       has_booking: bool, inbound_count: int) -> dict:
    """Deterministic fallback when the LLM is unavailable. Conservative but useful:
    a booking is hot; repeated engagement or an appointment intent is warm; else cold."""
    intents = {m.get("intent") for m in thread if m["direction"] == "out"}
    engaged = inbound_count >= 3 or "appointment" in intents
    if has_booking:
        band, score = "hot", 85
    elif engaged:
        band, score = "warm", 55
    else:
        band, score = "cold", 20
    return {
        "customer_name": patient_name,
        "requested_service": None,
        "appointment_preference": None,
        "insurance": None,
        "urgency": "medium" if engaged else "low",
        "sentiment": "neutral",
        "next_action": ("Confirm the upcoming appointment." if has_booking
                        else "Follow up to help the patient book." if engaged
                        else "No action needed yet."),
        "lead_band": band,
        "lead_score": score,
        "lead_rationale": "Heuristic score (AI analysis unavailable).",
    }


def _normalize(data: dict, fallback: dict) -> dict:
    """Coerce model output into the stored shape, backfilling from the heuristic."""
    out = dict(fallback)  # start from safe defaults
    for key in ("customer_name", "requested_service", "appointment_preference",
                "insurance", "next_action", "lead_rationale"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            out[key] = val.strip()[:500]
    if data.get("urgency") in URGENCY:
        out["urgency"] = data["urgency"]
    if data.get("sentiment") in SENTIMENT:
        out["sentiment"] = data["sentiment"]
    if data.get("lead_score") is not None:
        out["lead_score"] = _clamp_score(data["lead_score"])
    if data.get("lead_band") in LEAD_BANDS:
        out["lead_band"] = data["lead_band"]
    elif data.get("lead_score") is not None:
        out["lead_band"] = _band_for_score(out["lead_score"])
    return out


def analyze_conversation(thread: list[dict], patient_name: str | None,
                         has_booking: bool, inbound_count: int) -> tuple[dict, str]:
    """Return (analysis dict, source) where source is 'ai' or 'heuristic'."""
    fallback = heuristic_analysis(thread, patient_name, has_booking, inbound_count)
    transcript = _transcript(thread)
    if not transcript:
        return fallback, "heuristic"
    try:
        res = generate(_SYSTEM, [Msg(role="user", content=transcript)], [])
    except LLMUnavailable:
        return fallback, "heuristic"
    except Exception:  # noqa: BLE001 — analysis must never break the page
        log.exception("conversation analysis LLM call failed")
        return fallback, "heuristic"
    parsed = _extract_json(res.text or "")
    if not parsed:
        return fallback, "heuristic"
    return _normalize(parsed, fallback), "ai"


def staff_summary_line(a: dict | None) -> str:
    """A compact handover summary for staff (so they don't read 50 messages)."""
    if not a:
        return ""
    fields = [("Customer", a.get("customer_name")), ("Service", a.get("requested_service")),
              ("Preference", a.get("appointment_preference")), ("Insurance", a.get("insurance")),
              ("Urgency", a.get("urgency")), ("Sentiment", a.get("sentiment")),
              ("Next", a.get("next_action"))]
    return "\n".join(f"{label}: {val}" for label, val in fields if val)


def get_or_build(tenant_id: int, wa_user: str, force: bool = False) -> dict | None:
    """Cached analysis for a conversation. Rebuilds when the message count changed
    (new activity) or when forced. Returns the stored row, or None if no messages yet."""
    count = db.message_count(tenant_id, wa_user)
    cached = db.get_conversation_analysis(tenant_id, wa_user)
    if not force and cached and cached.get("message_count") == count:
        return cached
    if count == 0:
        return cached
    thread = db.conversation_thread(wa_user, tenant_id=tenant_id)
    name = db.get_patient_name(tenant_id, wa_user)
    has_booking = db.has_appointment(tenant_id, wa_user)
    inbound = sum(1 for m in thread if m["direction"] == "in")
    data, source = analyze_conversation(thread, name, has_booking, inbound)
    db.upsert_conversation_analysis(tenant_id, wa_user, data, count, source)
    return db.get_conversation_analysis(tenant_id, wa_user)
