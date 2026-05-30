"""Tests for configurable per-clinic booking intake fields."""
from app.tools import check_booking_fields

CD = {"booking_fields": [
    {"key": "device_code", "label": "Device code", "required": True},
    {"key": "insurance", "label": "Insurance ID", "required": False},
    {"key": "payment", "label": "Payment method", "required": True,
     "options": ["Cash", "Card", "mada"]},
]}


def test_missing_required_is_reported():
    err = check_booking_fields(CD, {"payment": "Cash"})
    assert err and err["error"] == "missing_information"
    assert "Device code" in err["needed"]


def test_all_required_present_passes():
    assert check_booking_fields(CD, {"device_code": "X1", "payment": "Cash"}) is None


def test_optional_field_can_be_omitted():
    assert check_booking_fields(CD, {"device_code": "X1", "payment": "mada"}) is None


def test_invalid_option_rejected():
    err = check_booking_fields(CD, {"device_code": "X1", "payment": "Bitcoin"})
    assert err and err["error"] == "invalid_value" and err["field"] == "Payment method"


def test_no_fields_configured_is_ok():
    assert check_booking_fields({}, {}) is None
    assert check_booking_fields({"booking_fields": []}, None) is None


def test_accepts_label_or_key_or_caseinsensitive():
    # model may pass the key, the label, or odd casing — all should validate
    assert check_booking_fields(CD, {"device_code": "X1", "payment": "Cash"}) is None
    assert check_booking_fields(CD, {"Device code": "X1", "Payment method": "mada"}) is None
    assert check_booking_fields(CD, {"DEVICE CODE": "X1", "PAYMENT METHOD": "Card"}) is None


def test_invalid_option_via_label():
    err = check_booking_fields(CD, {"Device code": "X1", "Payment method": "Bitcoin"})
    assert err and err["error"] == "invalid_value"
