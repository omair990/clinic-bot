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
TRANSCRIBE_PROVIDERS = [
    p.strip()
    for p in os.environ.get("TRANSCRIBE_PROVIDERS", "gemini,groq,openrouter,openai").split(",")
    if p.strip()
]
TRANSCRIBE_MODEL = os.getenv("TRANSCRIBE_MODEL", "gemini-2.5-flash")        # Gemini
GROQ_WHISPER_MODEL = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")
OPENAI_WHISPER_MODEL = os.getenv("OPENAI_WHISPER_MODEL", "whisper-1")
# OpenRouter has no Whisper endpoint; it transcribes via an audio-capable chat model.
OPENROUTER_TRANSCRIBE_MODEL = os.getenv("OPENROUTER_TRANSCRIBE_MODEL", "google/gemini-2.0-flash-001")

AI_PROVIDERS = [
    p.strip()
    for p in os.environ.get(
        "AI_PROVIDERS",
        "claude,mistral,openrouter,gemini,groq,deepseek,selfhosted").split(",")
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
ADMIN_WA_NUMBER = os.getenv("ADMIN_WA_NUMBER", "").strip()
PORT = int(os.getenv("PORT", "8000"))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-please-rotate")

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
