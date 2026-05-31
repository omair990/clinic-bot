"""Clinic-data schema: normalize + validate. Pure functions, no DB/network."""
import json
from pathlib import Path

from app import clinic_schema as cs


def _valid():
    return {
        "clinic": {"name": "Al-Shifa", "phone": "+966-11", "languages": ["Arabic", "English"]},
        "services": [{"name": "Checkup", "price_sar": 150, "duration_min": 20}],
        "doctors": [{"name": "Dr. Khalid", "specialty": "GP",
                     "available_days": ["Sunday", "Monday"], "available_hours": "5-9 PM"}],
        "appointment_policy": {"booking_lead_time_hours": 2, "walk_ins_accepted": True,
                               "payment_methods": ["Cash", "mada"]},
        "faqs": [{"q": "Insurance?", "a": "Yes."}],
    }


# --- happy path ---------------------------------------------------------------
def test_valid_data_passes_clean():
    _norm, errors, warnings = cs.validate_and_normalize(_valid())
    assert errors == []
    assert warnings == []


def test_shipped_sample_is_valid():
    """The canonical app/clinic_data.json must satisfy its own schema."""
    sample = json.loads((Path(__file__).resolve().parents[1] / "app" / "clinic_data.json").read_text())
    _n, errors, _w = cs.validate_and_normalize(sample)
    assert errors == [], errors


# --- required fields (these crash the live tools if missing) ------------------
def test_missing_clinic_name_errors():
    d = _valid(); d["clinic"].pop("name")
    _n, errors, _w = cs.validate_and_normalize(d)
    assert any("clinic.name" in e for e in errors)


def test_service_missing_price_errors():
    d = _valid(); d["services"][0].pop("price_sar")
    _n, errors, _w = cs.validate_and_normalize(d)
    assert any("services[0].price_sar" in e for e in errors)


def test_doctor_missing_required_fields_errors():
    d = _valid(); d["doctors"][0] = {"name": "Dr. X"}  # no specialty/days/hours
    _n, errors, _w = cs.validate_and_normalize(d)
    assert any("specialty" in e for e in errors)
    assert any("available_days" in e for e in errors)
    assert any("available_hours" in e for e in errors)


def test_faq_missing_answer_errors():
    d = _valid(); d["faqs"][0] = {"q": "Hours?"}
    _n, errors, _w = cs.validate_and_normalize(d)
    assert any("faqs[0].a" in e for e in errors)


# --- normalization (coercion of loose input) ----------------------------------
def test_numeric_strings_are_coerced():
    d = _valid(); d["services"][0]["price_sar"] = "150"; d["services"][0]["duration_min"] = "20"
    norm, errors, _w = cs.validate_and_normalize(d)
    assert norm["services"][0]["price_sar"] == 150
    assert norm["services"][0]["duration_min"] == 20
    assert errors == []


def test_non_numeric_price_stays_an_error():
    d = _valid(); d["services"][0]["price_sar"] = "free"
    _norm, errors, _w = cs.validate_and_normalize(d)
    assert any("price_sar" in e for e in errors)


def test_comma_string_becomes_list_and_days_titlecased():
    d = _valid()
    d["doctors"][0]["available_days"] = "sunday, monday, wednesday"
    norm, errors, _w = cs.validate_and_normalize(d)
    assert norm["doctors"][0]["available_days"] == ["Sunday", "Monday", "Wednesday"]
    assert errors == []


def test_walk_ins_string_coerced_to_bool():
    d = _valid(); d["appointment_policy"]["walk_ins_accepted"] = "true"
    norm, errors, _w = cs.validate_and_normalize(d)
    assert norm["appointment_policy"]["walk_ins_accepted"] is True
    assert errors == []


def test_empty_rows_are_dropped():
    d = _valid()
    d["services"].append({"name": "", "price_sar": "", "duration_min": ""})
    d["faqs"].append({"q": "", "a": ""})
    norm, errors, _w = cs.validate_and_normalize(d)
    assert len(norm["services"]) == 1
    assert len(norm["faqs"]) == 1
    assert errors == []


# --- pass-through (round-trip safety) -----------------------------------------
def test_unknown_sections_preserved():
    d = _valid()
    d["branches"] = [{"name": "Main", "city": "Riyadh"}]
    d["connector"] = {"type": "cliniko", "api_key": "x"}
    d["emergency_guidance"] = "Call 997."
    norm, _e, _w = cs.validate_and_normalize(d)
    assert norm["branches"] == [{"name": "Main", "city": "Riyadh"}]
    assert norm["connector"]["type"] == "cliniko"
    assert norm["emergency_guidance"] == "Call 997."


# --- warnings (soft, never block) ---------------------------------------------
def test_no_services_or_doctors_warns_not_errors():
    d = {"clinic": {"name": "Empty Clinic"}, "services": [], "doctors": [], "faqs": []}
    _n, errors, warnings = cs.validate_and_normalize(d)
    assert errors == []
    assert any("services" in w for w in warnings)
    assert any("doctors" in w for w in warnings)


def test_unknown_weekday_is_a_warning():
    d = _valid(); d["doctors"][0]["available_days"] = ["Funday"]
    _n, errors, warnings = cs.validate_and_normalize(d)
    assert errors == []
    assert any("Funday" in w for w in warnings)


def test_duplicate_service_name_warns():
    d = _valid()
    d["services"].append({"name": "checkup", "price_sar": 99, "duration_min": 10})
    _n, errors, warnings = cs.validate_and_normalize(d)
    assert errors == []
    assert any("duplicate" in w.lower() for w in warnings)


# --- robustness ---------------------------------------------------------------
def test_normalize_never_raises_on_garbage():
    for junk in (None, [], "string", 42, {"services": "not a list"}):
        cs.normalize(junk)  # must not raise


def test_non_dict_top_level_is_an_error():
    _n, errors, _w = cs.validate_and_normalize(["not", "a", "dict"])
    assert errors and "object" in errors[0]


def test_blank_template_is_a_sound_skeleton():
    """The reset skeleton is well-formed except for the name the user must fill in."""
    _n, errors, _w = cs.validate_and_normalize(cs.blank_template())
    assert errors == ["clinic.name: required (the clinic's display name)."]
