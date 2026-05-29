import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent

WA_ACCESS_TOKEN = os.environ["WA_ACCESS_TOKEN"]
WA_PHONE_NUMBER_ID = os.environ["WA_PHONE_NUMBER_ID"]
WA_VERIFY_TOKEN = os.environ["WA_VERIFY_TOKEN"]
WA_API_VERSION = os.getenv("WA_API_VERSION", "v22.0")
WA_APP_SECRET = os.environ.get("WA_APP_SECRET", "")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

AI_PROVIDERS = [
    p.strip() for p in os.environ.get("AI_PROVIDERS", "gemini,groq,deepseek").split(",") if p.strip()
]

ADMIN_WA_NUMBER = os.getenv("ADMIN_WA_NUMBER", "")

PORT = int(os.getenv("PORT", "8000"))

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-please-rotate")

# Outbound webhooks (n8n etc) — leave blank to disable
N8N_NEW_APPOINTMENT_URL = os.environ.get("N8N_NEW_APPOINTMENT_URL", "")
N8N_EMERGENCY_URL = os.environ.get("N8N_EMERGENCY_URL", "")

DB_PATH = Path(os.environ.get("DB_PATH", BASE_DIR.parent / "clinic.db"))
CLINIC_DATA_PATH = BASE_DIR / "clinic_data.json"

with open(CLINIC_DATA_PATH) as f:
    CLINIC_DATA = json.load(f)
