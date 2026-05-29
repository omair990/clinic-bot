"""Simulate a real WhatsApp conversation through the live agent + LLM + Postgres.
Run with DATABASE_URL pointing at a test DB. Uses the real provider chain."""
import time

from app import db
from app.agent import run_agent

PACE_SECONDS = 12  # space turns out to respect free-tier rate limits

USER = "966500111222"

SCRIPT = [
    "Hi! How much is a dental checkup and a cleaning?",
    "Great. What times does Dr. Hassan have next Monday for a dental checkup?",
    "Book the earliest one please. My name is Omar Al-Faraj.",
    "What appointments do I have?",
    "I'm having severe chest pain and trouble breathing right now",
]


def turn(text: str) -> None:
    history = db.recent_history(USER, 12)
    db.log_message(USER, "in", text)
    print("\n" + "=" * 70)
    print(f"PATIENT > {text}")
    try:
        ctx = run_agent(USER, text, history)
    except Exception as e:  # noqa: BLE001
        print(f"AGENT   > [provider error: {type(e).__name__}]")
        return
    db.log_message(USER, "out", ctx.reply, ctx.derived_intent(), ctx.needs_human)
    print(f"AGENT   > {ctx.reply}")
    meta = f"intent={ctx.derived_intent()} needs_human={ctx.needs_human}"
    if ctx.actions:
        meta += f" actions={ctx.actions}"
    print(f"         [{meta}]")


def main() -> None:
    db.init_db()
    for i, msg in enumerate(SCRIPT):
        if i:
            time.sleep(PACE_SECONDS)
        turn(msg)
    print("\n" + "=" * 70)
    print("Appointments in DB:")
    for a in db.list_appointments():
        print(f"  #{a['id']} {a['patient_name']} | {a['doctor']} | {a['service']} "
              f"| {a['start_at']} | {a['status']}")


if __name__ == "__main__":
    main()
