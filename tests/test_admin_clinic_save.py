"""The admin clinic-data save path (_parse_clinic_data): validate-on-save. No DB needed."""
import json

import pytest

from app.admin import ClinicDataError, _parse_clinic_data


def test_empty_box_means_no_clinic_data():
    assert _parse_clinic_data("") == (None, [])
    assert _parse_clinic_data("   ") == (None, [])


def test_valid_data_normalizes_and_returns_warnings():
    raw = json.dumps({"clinic": {"name": "X"},
                      "services": [{"name": "A", "price_sar": "150", "duration_min": "20"}],
                      "doctors": [], "faqs": []})
    norm, warnings = _parse_clinic_data(raw)
    assert norm["services"][0]["price_sar"] == 150        # coerced
    assert any("doctors" in w for w in warnings)          # advisory, did not block


def test_missing_required_fields_block_the_save():
    raw = json.dumps({"clinic": {}, "services": [{"name": "A"}]})
    with pytest.raises(ClinicDataError) as ei:
        _parse_clinic_data(raw)
    assert any("clinic.name" in e for e in ei.value.errors)
    assert any("price_sar" in e for e in ei.value.errors)


def test_bad_json_is_rejected_not_silently_accepted():
    with pytest.raises(ClinicDataError) as ei:
        _parse_clinic_data("{not json")
    assert ei.value.errors and "Invalid JSON" in ei.value.errors[0]


def test_pass_through_sections_survive_the_save():
    raw = json.dumps({"clinic": {"name": "X"}, "services": [], "doctors": [], "faqs": [],
                      "connector": {"type": "cliniko", "api_key": "k"},
                      "branches": [{"name": "Main", "city": "Riyadh"}]})
    norm, _w = _parse_clinic_data(raw)
    assert norm["connector"]["type"] == "cliniko"
    assert norm["branches"][0]["city"] == "Riyadh"
