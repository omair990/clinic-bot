"""Realistic end-to-end scenario tests — drives the real agent + live model against
a staging clinic, using natural patient phrasings. Not a pytest (needs a real LLM key).

Run:  scripts/staging.sh init && \
      DATABASE_URL=... AI_PROVIDERS=mistral,openrouter MISTRAL_API_KEY=... \
      python scripts/scenario_test.py
"""
import logging
import uuid

logging.basicConfig(level=logging.WARNING)
logging.getLogger("app.tools").setLevel(logging.INFO)  # show tool calls

from app.agent import run_agent  # noqa: E402
from app.db import close_db, create_tenant, init_db  # noqa: E402

CLINIC = {
    "clinic": {"name": "Al-Shifa Family Clinic", "address": "King Fahd Rd, Riyadh",
               "phone": "+96611000000"},
    "doctors": [
        {"name": "Dr. Khalid Al-Otaibi", "specialty": "General Practitioner",
         "available_days": ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"],
         "available_hours": "9:00 AM - 1:00 PM, 5:00 PM - 9:00 PM"},
        {"name": "Dr. Sara Al-Subaie", "specialty": "Dentist",
         "available_days": ["Sunday", "Tuesday", "Thursday"],
         "available_hours": "10:00 AM - 2:00 PM"},
        {"name": "Dr. Layla Al-Ghamdi", "specialty": "Dermatologist",
         "available_days": ["Monday", "Wednesday"], "available_hours": "4:00 PM - 8:00 PM"},
    ],
    "services": [
        {"name": "General Consultation", "price_sar": 150, "duration_min": 20},
        {"name": "Dental Cleaning", "price_sar": 250, "duration_min": 30},
        {"name": "Dental Checkup", "price_sar": 120, "duration_min": 20},
        {"name": "Skin Consultation", "price_sar": 300, "duration_min": 30},
    ],
    "appointment_policy": {"payment_methods": ["Cash", "mada", "Card", "Insurance"],
                           "booking_lead_time_hours": 2,
                           "cancellation_policy": "Cancel at least 4 hours before."},
    "faqs": [
        {"q": "Do you accept insurance?", "a": "Yes, we accept Bupa and Tawuniya."},
        {"q": "Is there parking?", "a": "Yes, free parking is available."},
        {"q": "Do you offer home service?", "a": "No, we do not offer home visits."},
    ],
    "booking_fields": [{"key": "payment", "label": "Payment method", "required": True,
                        "options": ["Cash", "mada", "Card", "Insurance"]}],
}

SCENARIOS = [
    ("Greeting", ["hello"]),
    ("Pricing - cleaning", ["how much is a dental cleaning?"]),
    ("Pricing - typo/loose", ["whats the consultaion fee"]),
    ("Working hours", ["what time are you open?"]),
    ("Location", ["where are you located"]),
    ("Insurance FAQ", ["do you take insurance?"]),
    ("Home service FAQ", ["do you do home visits?"]),
    ("Out of scope - weather", ["whats the weather like today"]),
    ("Out of scope - medical advice", ["i have a headache, what pill should i take?"]),
    ("Emergency", ["help i have severe chest pain and cant breathe"]),
    ("Fake doctor", ["i want to book with dr fatima tomorrow"]),
    ("Arabic pricing", ["كم سعر تنظيف الأسنان؟"]),
    ("Vague booking", ["i need to see someone"]),
    ("Booking happy path", [
        "i'd like to book a dental cleaning",
        "with dr sara",
        "this sunday morning",
        "10am works",
        "Ahmed Ali, paying by mada",
    ]),
    ("Reschedule then cancel", [
        "i want a general consultation tomorrow",
        "dr khalid, 9am",
        "name is Omar, cash",
        "actually cancel that",
    ]),
]


def run():
    init_db()
    tid = create_tenant("Scenario Clinic", "scn-" + uuid.uuid4().hex[:6], "PNSCN",
                        None, "Asia/Riyadh", None, CLINIC)
    tenant = {"id": tid, "clinic_data": CLINIC, "slug": "scn"}
    for title, turns in SCENARIOS:
        print("\n" + "=" * 70)
        print(f"SCENARIO: {title}  (user={('966' + uuid.uuid4().hex[:6])})")
        print("=" * 70)
        user = "966" + uuid.uuid4().hex[:7]
        history: list[dict] = []
        for msg in turns:
            print(f"\n  USER: {msg}")
            ctx = run_agent(tenant, user, msg, history)
            flags = []
            if ctx.emergency:
                flags.append("EMERGENCY")
            if ctx.needs_human:
                flags.append("HANDOVER")
            if ctx.booked_ids:
                flags.append(f"booked={ctx.booked_ids}")
            if ctx.changed_ids:
                flags.append(f"changed={ctx.changed_ids}")
            tag = ("  [" + ", ".join(flags) + "]") if flags else ""
            print(f"  BOT : {ctx.reply}{tag}")
            history.append({"direction": "in", "message": msg})
            history.append({"direction": "out", "message": ctx.reply})
    close_db()


if __name__ == "__main__":
    run()
