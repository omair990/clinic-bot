"""Per-clinic default agent language: prompt injection + schema handling."""
from app import prompts, clinic_schema


def test_prompt_injects_default_language_when_set():
    cd = {"clinic": {"name": "Test", "languages": ["Arabic", "English"], "default_language": "Arabic"}}
    p = prompts.build_system_prompt(cd)
    assert "default to Arabic" in p


def test_prompt_has_no_default_note_when_unset():
    p = prompts.build_system_prompt({"clinic": {"name": "Test"}})
    # The default-language fallback sentence only appears when a clinic sets one.
    assert "default to " not in p.split("CONVERSATION RULES")[1][:700]


def test_schema_normalizes_and_keeps_default_language():
    norm, errors, _ = clinic_schema.validate_and_normalize(
        {"clinic": {"name": "X", "languages": ["English"], "default_language": "  English  "}})
    assert norm["clinic"]["default_language"] == "English"
    assert errors == []


def test_schema_warns_when_default_not_in_languages():
    _, errors, warnings = clinic_schema.validate_and_normalize(
        {"clinic": {"name": "X", "languages": ["English"], "default_language": "Arabic"}})
    assert errors == []  # soft: never blocks the save
    assert any("default_language" in w for w in warnings)


def test_blank_template_has_default_language():
    assert clinic_schema.blank_template()["clinic"]["default_language"] == "Arabic"
