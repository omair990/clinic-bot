"""Edge-case / adversarial scenario batch."""
import logging
import uuid

logging.basicConfig(level=logging.WARNING)
logging.getLogger("app.tools").setLevel(logging.INFO)

from app.agent import run_agent  # noqa: E402
from app.db import close_db, create_tenant, init_db  # noqa: E402
from scripts.scenario_test import CLINIC  # noqa: E402

SCENARIOS = [
    ("Past date", ["i want to book a general consultation last monday"]),
    ("Past time today", ["book dr khalid today at 5am"]),
    ("Out of clinic hours", ["book dr sara tomorrow at 3am"]),
    ("Invalid service", ["i'd like to book a haircut please"]),
    ("Gibberish", ["asdkjfh qwerty zxcvb"]),
    ("Emoji only", ["😀😀👍🔥"]),
    ("Nonsense date", ["book a consultation on the 45th of June"]),
    ("Mixed language", ["ابغى book موعد بكرة with dr khalid at 10am, name Ali, cash"]),
    ("Booking for someone else", [
        "i want to book for my mother Aisha, dental cleaning with dr sara this sunday 10am, mada",
    ]),
    ("Double-book same slot", [
        "book a dental cleaning with dr sara this sunday at 12pm, name Mona, cash",
        "book another dental cleaning with dr sara this sunday at 12pm, name Nora, cash",
    ]),
    ("Very long rambling message", [
        "hi so um i was thinking maybe i should come in because my tooth has been bothering "
        "me for a while now and also my cousin recommended you and anyway i think i need a "
        "dental cleaning can you book me with dr sara sometime sunday morning my name is "
        "Khalid and i'll pay with mada thanks so much really appreciate it",
    ]),
    ("Contradictory / mind change", [
        "book me with dr sara sunday 10am",
        "no wait, make it dr khalid for a general consultation tomorrow 9am instead",
        "name Yousef, cash",
    ]),
]


def run():
    init_db()
    tid = create_tenant("Edge Clinic", "eg-" + uuid.uuid4().hex[:6], "PNEG",
                        None, "Asia/Riyadh", None, CLINIC)
    tenant = {"id": tid, "clinic_data": CLINIC, "slug": "eg"}
    for title, turns in SCENARIOS:
        print("\n" + "=" * 70)
        print(f"SCENARIO: {title}")
        print("=" * 70)
        user = "966" + uuid.uuid4().hex[:7]
        history: list[dict] = []
        for msg in turns:
            short = msg if len(msg) < 90 else msg[:87] + "..."
            print(f"\n  USER: {short}")
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
