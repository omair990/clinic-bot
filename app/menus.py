"""Interactive WhatsApp menu builders sourced from clinic_data.json."""
from app.config import CLINIC_DATA

MAIN_MENU_BUTTONS = [
    {"id": "menu_book", "title": "Book Appointment"},
    {"id": "menu_services", "title": "View Services"},
    {"id": "menu_human", "title": "Talk to Staff"},
]


def main_menu_body() -> str:
    return f"How can I help you today at {CLINIC_DATA['clinic']['name']}?"


def services_list_rows() -> list[dict]:
    rows = []
    for svc in CLINIC_DATA["services"][:10]:
        rows.append({
            "id": f"svc_{svc['name'].lower().replace(' ', '_')}",
            "title": svc["name"],
            "description": f"SAR {svc['price_sar']} · {svc['duration_min']} min",
        })
    return rows


def doctors_list_rows() -> list[dict]:
    rows = []
    for doc in CLINIC_DATA["doctors"][:10]:
        rows.append({
            "id": f"doc_{doc['name'].lower().replace(' ', '_').replace('.', '')}",
            "title": doc["name"],
            "description": doc["specialty"],
        })
    return rows
