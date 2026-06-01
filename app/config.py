"""Centralised, validated configuration. Fails fast on missing required env."""
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent


def _require(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return val


# --- WhatsApp Cloud API ---
WA_ACCESS_TOKEN = _require("WA_ACCESS_TOKEN")
WA_PHONE_NUMBER_ID = _require("WA_PHONE_NUMBER_ID")
WA_VERIFY_TOKEN = _require("WA_VERIFY_TOKEN")
WA_API_VERSION = os.getenv("WA_API_VERSION", "v22.0")
WA_APP_SECRET = os.environ.get("WA_APP_SECRET", "").strip()

# --- LLM providers ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "").strip()
# ElevenLabs powers both Scribe STT (inbound voice notes) and TTS (spoken replies).
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "").strip()

# Self-hosted / "own" model via any OpenAI-compatible server (Ollama, vLLM, RunPod
# serverless). The always-available tail of the chain — no per-token credit to run out of.
SELFHOSTED_BASE_URL = os.environ.get("SELFHOSTED_BASE_URL", "").strip()
SELFHOSTED_API_KEY = os.environ.get("SELFHOSTED_API_KEY", "").strip()

# High-performance models per provider (all overridable via env).
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-large-latest")
SELFHOSTED_MODEL = os.getenv("SELFHOSTED_MODEL", "qwen2.5:14b-instruct")

# Voice notes: transcription fallback chain (tried in order, missing keys skipped).
# ElevenLabs Scribe is primary; Gemini is the fallback (works from cloud IPs, unlike
# ElevenLabs' free tier — keep it until ElevenLabs is on a paid plan).
TRANSCRIBE_PROVIDERS = [
    p.strip()
    for p in os.environ.get(
        "TRANSCRIBE_PROVIDERS", "elevenlabs,gemini").split(",")
    if p.strip()
]
TRANSCRIBE_MODEL = os.getenv("TRANSCRIBE_MODEL", "gemini-2.5-flash")        # Gemini
GROQ_WHISPER_MODEL = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")
OPENAI_WHISPER_MODEL = os.getenv("OPENAI_WHISPER_MODEL", "whisper-1")
# OpenRouter has no Whisper endpoint; it transcribes via an audio-capable chat model.
OPENROUTER_TRANSCRIBE_MODEL = os.getenv("OPENROUTER_TRANSCRIBE_MODEL", "google/gemini-2.0-flash-001")
ELEVENLABS_STT_MODEL = os.getenv("ELEVENLABS_STT_MODEL", "scribe_v1")

# --- Spoken replies (ElevenLabs TTS) ---
# When a patient sends a voice note we can reply with a voice note (modality mirroring).
# Off by default: it costs per character, so opt in per deploy and/or per clinic
# (clinic_data.voice.enabled). Replies longer than the cap fall back to text.
VOICE_REPLY_ENABLED = os.getenv("VOICE_REPLY_ENABLED", "false").lower() in ("1", "true", "yes", "on")
VOICE_REPLY_MAX_CHARS = int(os.getenv("VOICE_REPLY_MAX_CHARS", "600"))
ELEVENLABS_TTS_MODEL = os.getenv("ELEVENLABS_TTS_MODEL", "eleven_multilingual_v2")
# A multilingual default voice (handles Arabic + English). Override per clinic.
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")
# WhatsApp shows ogg/opus as a push-to-talk voice note; mp3 plays as a generic audio clip.
ELEVENLABS_TTS_FORMAT = os.getenv("ELEVENLABS_TTS_FORMAT", "opus")  # "opus" | "mp3"

AI_PROVIDERS = [
    p.strip()
    for p in os.environ.get(
        "AI_PROVIDERS",
        # Claude primary; Gemini ahead of Mistral as the stronger, better-grounded fallback.
        "claude,gemini,mistral").split(",")
    if p.strip()
]

# Max tool-calling round-trips per user turn before we hand off to staff.
AGENT_MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "6"))

# --- Background maintenance (auto-prune) ---
MAINTENANCE_INTERVAL_HOURS = int(os.getenv("MAINTENANCE_INTERVAL_HOURS", "24"))
PROCESSED_MSG_RETENTION_HOURS = int(os.getenv("PROCESSED_MSG_RETENTION_HOURS", "24"))
EVENT_RETENTION_DAYS = int(os.getenv("EVENT_RETENTION_DAYS", "30"))


def _flag(name: str, default: bool) -> bool:
    return os.getenv(name, "true" if default else "false").lower() in ("1", "true", "yes", "on")


# --- No-show recovery & risk prediction ---
# Master switch for the no-show feature (detection sweep + recovery outreach).
NO_SHOW_ENABLED = _flag("NO_SHOW_ENABLED", True)
# Auto-send the recovery WhatsApp the moment a no-show is detected. When off, staff
# send it manually from the No-shows dashboard ("Both" mode keeps manual controls either way).
NO_SHOW_AUTO_SEND = _flag("NO_SHOW_AUTO_SEND", True)
# How long after an appointment's end time we treat a still-confirmed booking as a no-show.
NO_SHOW_GRACE_MINUTES = int(os.getenv("NO_SHOW_GRACE_MINUTES", "30"))
# How often the background sweep runs.
NO_SHOW_SWEEP_INTERVAL_MIN = int(os.getenv("NO_SHOW_SWEEP_INTERVAL_MIN", "15"))
# Silence windows before the day-later follow-up, then before marking the lead inactive.
NO_SHOW_FOLLOWUP_HOURS = int(os.getenv("NO_SHOW_FOLLOWUP_HOURS", "24"))
NO_SHOW_INACTIVE_HOURS = int(os.getenv("NO_SHOW_INACTIVE_HOURS", "24"))
# Premium predictor: score upcoming appointments and send high-risk patients an extra
# reminder this many hours before the appointment.
NO_SHOW_PREDICTOR = _flag("NO_SHOW_PREDICTOR", True)
NO_SHOW_RISK_REMINDER_LEAD_HOURS = int(os.getenv("NO_SHOW_RISK_REMINDER_LEAD_HOURS", "24"))

# Proactive (business-initiated) WhatsApp messages outside the 24-hour customer-care
# window require a PRE-APPROVED message template. Turn this on once the templates below
# are registered & approved in your WhatsApp Business account; until then the no-show
# messages send as free-form text (fine in dev / inside the 24h window).
# A clinic can override the names/language per-tenant via clinic_data.no_show_templates:
#   {"no_show": "...", "followup": "...", "reminder": "...", "language": "en"}
# Expected body variables: no_show/followup -> {{1}} appointment summary;
#   reminder -> {{1}} appointment summary, {{2}} date & time.
NO_SHOW_USE_TEMPLATES = _flag("NO_SHOW_USE_TEMPLATES", False)
NO_SHOW_TEMPLATE_LANG = os.getenv("NO_SHOW_TEMPLATE_LANG", "en")
WA_TEMPLATE_NO_SHOW = os.getenv("WA_TEMPLATE_NO_SHOW", "").strip()
WA_TEMPLATE_FOLLOWUP = os.getenv("WA_TEMPLATE_FOLLOWUP", "").strip()
WA_TEMPLATE_REMINDER = os.getenv("WA_TEMPLATE_REMINDER", "").strip()

# --- Scheduled Business-Insights digest (Phase 5 delivery) ---
# Sends each clinic owner a daily (and weekly) insights summary over WhatsApp. The owner
# number is clinic_data.owner_wa_number per tenant, falling back to ADMIN_WA_NUMBER for the
# platform's own clinic. Hour is in the tenant's local timezone; weekly DOW is Python's
# Mon=0..Sun=6 (default Sunday).
INSIGHTS_DIGEST_ENABLED = _flag("INSIGHTS_DIGEST_ENABLED", True)
INSIGHTS_DIGEST_HOUR = int(os.getenv("INSIGHTS_DIGEST_HOUR", "8"))
INSIGHTS_WEEKLY_DOW = int(os.getenv("INSIGHTS_WEEKLY_DOW", "6"))
INSIGHTS_DIGEST_INTERVAL_MIN = int(os.getenv("INSIGHTS_DIGEST_INTERVAL_MIN", "30"))

# WhatsApp the patient when staff cancel or complete their appointment from the dashboard.
NOTIFY_ON_STATUS_CHANGE = _flag("NOTIFY_ON_STATUS_CHANGE", True)

# Pre-appointment confirmation: ask EVERY upcoming patient "will you attend?" (confirm /
# reschedule / cancel) this many hours before their appointment. Cuts no-shows up front.
PRE_APPT_CONFIRM_ENABLED = _flag("PRE_APPT_CONFIRM_ENABLED", True)
PRE_APPT_CONFIRM_LEAD_HOURS = int(os.getenv("PRE_APPT_CONFIRM_LEAD_HOURS", "24"))

# --- Clinic connectors (integration layer) ---
# Platform-level Google OAuth app credentials. A tenant opts into the Google Calendar
# connector via clinic_data.connector = {"type":"google_calendar","refresh_token":"…",
# "calendars":{"Dr. Khalid Al-Otaibi":"<calendarId>"}, "timezone":"Asia/Riyadh"}.
GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()

# --- LLM resilience ---
# Per-call wall-clock budget for any single provider request (seconds). Stops a
# slow/hung provider from holding a worker thread (Anthropic's SDK default is 600s).
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "30"))
# Cap reply length (WhatsApp messages are short) and stop the model from role-playing
# extra turns / simulating the user — the cause of long rambling replies.
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "500"))
LLM_STOP = ["\nUser:", "\nuser:", "\nPatient:", "User hasn't"]
# Circuit breaker: after this many consecutive failures a provider is skipped for
# the cooldown window, so a dead provider (e.g. no credits) isn't retried on every
# message — we go straight to the next one.
LLM_BREAKER_THRESHOLD = int(os.getenv("LLM_BREAKER_THRESHOLD", "3"))
LLM_BREAKER_COOLDOWN_S = float(os.getenv("LLM_BREAKER_COOLDOWN_S", "60"))

# --- Operations ---
# Master switch for plan/quota enforcement (counting always happens regardless).
USAGE_ENFORCEMENT = os.getenv("USAGE_ENFORCEMENT", "true").lower() in ("1", "true", "yes", "on")
# By default the platform's own 'default' clinic is exempt from plan/quota/status enforcement
# (so a dashboard misclick can't lock out the operator). Set this true to also enforce the
# plan on the default clinic — e.g. a single-tenant deployment that wants its own limits.
ENFORCE_DEFAULT_TENANT = os.getenv("ENFORCE_DEFAULT_TENANT", "false").lower() in ("1", "true", "yes", "on")
ADMIN_WA_NUMBER = os.getenv("ADMIN_WA_NUMBER", "").strip()

# --- Provider health monitor ---
# Raise an incident (and WhatsApp ADMIN_WA_NUMBER) when the primary LLM provider stays down
# this long — so a silent fallback-only degradation (e.g. Claude credits exhausted) is noticed.
PROVIDER_MONITOR_ENABLED = os.getenv(
    "PROVIDER_MONITOR_ENABLED", "true").lower() in ("1", "true", "yes", "on")
LLM_OUTAGE_ALERT_MIN = int(os.getenv("LLM_OUTAGE_ALERT_MIN", "30"))
PROVIDER_MONITOR_INTERVAL_MIN = int(os.getenv("PROVIDER_MONITOR_INTERVAL_MIN", "5"))
PORT = int(os.getenv("PORT", "8000"))
# Deployed commit — Railway injects RAILWAY_GIT_COMMIT_SHA on GitHub deploys; surfaced on
# the health endpoint so the running version is verifiable.
COMMIT_SHA = (os.environ.get("RAILWAY_GIT_COMMIT_SHA")
              or os.environ.get("GIT_COMMIT") or "unknown").strip()[:12]
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-please-rotate")
# Encryption key for secrets at rest (WhatsApp token, connector credentials). A Fernet key;
# if unset it's derived from SECRET_KEY. Set a stable dedicated value in production — changing
# it makes existing encrypted secrets unrecoverable.
SECRETS_KEY = os.environ.get("SECRETS_KEY", "").strip()

# --- Database (Postgres) ---
# Railway/Heroku style URLs use the `postgres://` scheme; psycopg wants `postgresql://`.
DATABASE_URL = _require("DATABASE_URL")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))

# --- Clinic domain data & timezone ---
CLINIC_DATA_PATH = BASE_DIR / "clinic_data.json"
with open(CLINIC_DATA_PATH, encoding="utf-8") as f:
    CLINIC_DATA = json.load(f)

TIMEZONE = os.getenv("CLINIC_TIMEZONE", "Asia/Riyadh")
TZ = ZoneInfo(TIMEZONE)

_policy = CLINIC_DATA.get("appointment_policy", {})
BOOKING_LEAD_HOURS = int(_policy.get("booking_lead_time_hours", 2))
SLOT_GRANULARITY_MIN = int(os.getenv("SLOT_GRANULARITY_MIN", "15"))
