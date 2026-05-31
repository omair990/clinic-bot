"""Unit tests for returning-patient memory in the system prompt (no DB)."""
from datetime import datetime

from app.config import TZ
from app.prompts import build_system_prompt


def test_prompt_includes_returning_patient_history():
    hist = [{"doctor": "Dr. Ahmed", "service": "Dermatology",
             "start_at": datetime(2026, 4, 1, 17, 0, tzinfo=TZ), "status": "completed"}]
    p = build_system_prompt(patient_name="Sara", history=hist)
    assert "RETURNING PATIENT" in p
    assert "Dr. Ahmed" in p and "Dermatology" in p


def test_prompt_has_no_history_block_when_empty():
    p = build_system_prompt(patient_name="Sara", history=[])
    assert "RETURNING PATIENT" not in p
    p2 = build_system_prompt(patient_name="Sara")
    assert "RETURNING PATIENT" not in p2


def test_prompt_includes_pending_review_block():
    p = build_system_prompt(review={"appointment_id": 5, "service": "Consult", "doctor": "Dr. R"})
    assert "REVIEW REQUEST PENDING" in p and "record_review" in p


def test_prompt_no_review_block_when_absent():
    assert "REVIEW REQUEST PENDING" not in build_system_prompt(patient_name="Sara")
