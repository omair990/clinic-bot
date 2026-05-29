"""Provide the env vars that app.config requires at import time, so the pure
scheduling logic can be imported and tested without real credentials or a DB."""
import os

os.environ.setdefault("WA_ACCESS_TOKEN", "test")
os.environ.setdefault("WA_PHONE_NUMBER_ID", "test")
os.environ.setdefault("WA_VERIFY_TOKEN", "test")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("GEMINI_API_KEY", "")
