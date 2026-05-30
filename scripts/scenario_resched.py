"""Rescheduling-focused scenario batch."""
import logging
import uuid

logging.basicConfig(level=logging.WARNING)
logging.getLogger("app.tools").setLevel(logging.INFO)

from app.agent import run_agent  # noqa: E402
from app.db import close_db, create_tenant, init_db  # noqa: E402
from scripts.scenario_test import CLINIC  # noqa: E402

SCENARIOS = [
    ("Reschedule same day to a later time", [
        "i want a general consultation tomorrow",
        "dr khalid at 9am",
        "my name is Omar, paying cash",
        "actually can we make it 11am instead?",
    ]),
    ("Reschedule to another day", [
        "book a dental cleaning with dr sara this sunday at 10am",
        "name is Lena, mada",
        "can you move it to thursday same time?",
    ]),
    ("Reschedule to a day the doctor doesn't work (should reject)", [
        "book a dental cleaning with dr sara this sunday 11am",
        "name Huda, cash",
        "move it to monday please",
    ]),
    ("Multiple appointments - reschedule the right one", [
        "book a general consultation tomorrow with dr khalid at 9am, name Faisal, cash",
        "also book a dental cleaning with dr sara this thursday at 10am, mada",
        "please reschedule my dental appointment to 11am",
    ]),
    ("Reschedule with no appointment", [
        "i want to change my appointment time",
    ]),
    ("Arabic reschedule", [
        "احجز استشارة عامة مع دكتور خالد بكرة الساعة ٩",
        "اسمي سعد، كاش",
        "أبغى أغير الموعد إلى الساعة ١١",
    ]),
]


def run():
    init_db()
    tid = create_tenant("Resched Clinic", "rs-" + uuid.uuid4().hex[:6], "PNRS",
                        None, "Asia/Riyadh", None, CLINIC)
    tenant = {"id": tid, "clinic_data": CLINIC, "slug": "rs"}
    for title, turns in SCENARIOS:
        print("\n" + "=" * 70)
        print(f"SCENARIO: {title}")
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
