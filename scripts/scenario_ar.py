"""Arabic end-to-end scenario batch — realistic Saudi-Arabic patient phrasings."""
import logging
import uuid

logging.basicConfig(level=logging.WARNING)
logging.getLogger("app.tools").setLevel(logging.INFO)

from app.agent import run_agent  # noqa: E402
from app.db import close_db, create_tenant, init_db  # noqa: E402
from scripts.scenario_test import CLINIC  # noqa: E402

SCENARIOS = [
    ("تحية", ["السلام عليكم"]),
    ("سعر تنظيف", ["كم سعر تنظيف الأسنان؟"]),
    ("الدوام", ["متى دوام العيادة؟"]),
    ("الموقع", ["وين موقعكم؟"]),
    ("التأمين", ["هل تقبلون تأمين؟"]),
    ("خارج النطاق", ["كيف الطقس اليوم؟"]),
    ("طوارئ", ["عندي ألم شديد في الصدر ومو قادر أتنفس"]),
    ("دكتور غير موجود", ["أبغى أحجز مع دكتورة فاطمة بكرة"]),
    ("حجز كامل (أرقام عربية + مدى)", [
        "أبغى أحجز تنظيف أسنان",
        "مع دكتورة سارة",
        "الأحد الصبح",
        "الساعة ١٠",
        "اسمي أحمد علي وأدفع مدى",
    ]),
    ("حجز ثم إلغاء", [
        "أبغى موعد استشارة عامة بكرة",
        "دكتور خالد الساعة ٩ الصبح",
        "اسمي عمر، كاش",
        "لا خلاص ألغ الموعد",
    ]),
]


def run():
    init_db()
    tid = create_tenant("AR Clinic", "ar-" + uuid.uuid4().hex[:6], "PNAR",
                        None, "Asia/Riyadh", None, CLINIC)
    tenant = {"id": tid, "clinic_data": CLINIC, "slug": "ar"}
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
