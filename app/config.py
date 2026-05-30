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

# Self-hosted / "own" model via any OpenAI-compatible server (Ollama, vLLM, RunPod
# serverless). The always-available tail of the chain — no per-token credit to run out of.
SELFHOSTED_BASE_URL = os.environ.get("SELFHOSTED_BASE_URL", "").strip()
SELFHOSTED_API_KEY = os.environ.get("SELFHOSTED_API_KEY", "").strip()

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
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
        "AI_PROVIDERS", "gemini,openrouter,claude,groq,deepseek,selfhosted").split(",")
    if p.strip()
]

# Max tool-calling round-trips per user turn before we hand off to staff.
AGENT_MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "6"))

# --- LLM resilience ---
# Per-call wall-clock budget for any single provider request (seconds). Stops a
# slow/hung provider from holding a worker thread (Anthropic's SDK default is 600s).
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "30"))
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
