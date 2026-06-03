"""_enrich_clinic_data: additive merge of aliases/specialty/requires_doctor onto a tenant's
clinic_data by exact name. Must fill only missing fields and never touch existing data."""
from app.db import _enrich_clinic_data

TMPL_SERVICES = [
    {"name": "Dental Cleaning", "price_sar": 400, "duration_min": 45,
     "specialty": "Dentist", "aliases": ["تنظيف الأسنان"]},
    {"name": "Lab Test - Blood Sugar", "price_sar": 50, "duration_min": 10,
     "requires_doctor": False, "aliases": ["فحص السكر"]},
]
TMPL_DOCTORS = [
    {"name": "Dr. Hassan Al-Qahtani", "specialty": "Dentist",
     "aliases": ["حسن القحطاني"]},
]


def test_fills_missing_fields_only_and_preserves_existing():
    # Live config: doctor with an admin-edited availability; service with no enrichment yet.
    data = {
        "services": [
            {"name": "Dental Cleaning", "price_sar": 400, "duration_min": 45},
            {"name": "Lab Test - Blood Sugar", "price_sar": 50, "duration_min": 10},
        ],
        "doctors": [
            {"name": "Dr. Hassan Al-Qahtani", "specialty": "Dentist",
             "available_days": ["Saturday"], "available_hours": "9:00 AM - 5:00 PM"},
        ],
    }
    out, changed = _enrich_clinic_data(data, TMPL_SERVICES, TMPL_DOCTORS)
    assert changed
    assert out["services"][0]["aliases"] == ["تنظيف الأسنان"]
    assert out["services"][0]["specialty"] == "Dentist"
    assert out["services"][1]["requires_doctor"] is False
    assert out["doctors"][0]["aliases"] == ["حسن القحطاني"]
    # The admin's availability edit is untouched.
    assert out["doctors"][0]["available_days"] == ["Saturday"]


def test_never_overwrites_and_is_idempotent():
    data = {"services": [{"name": "Dental Cleaning", "aliases": ["custom"], "specialty": "Custom"}],
            "doctors": []}
    out, changed = _enrich_clinic_data(data, TMPL_SERVICES, TMPL_DOCTORS)
    assert not changed                                   # nothing missing to fill
    assert out["services"][0]["aliases"] == ["custom"]   # existing value preserved
    assert out["services"][0]["specialty"] == "Custom"


def test_unknown_names_are_left_alone():
    data = {"services": [{"name": "Acupuncture", "price_sar": 200}], "doctors": []}
    out, changed = _enrich_clinic_data(data, TMPL_SERVICES, TMPL_DOCTORS)
    assert not changed
    assert "aliases" not in out["services"][0]
