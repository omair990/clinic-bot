"""Tests for Markdown -> WhatsApp formatting."""
from app.formatting import to_whatsapp


def test_double_asterisk_bold_becomes_single():
    assert to_whatsapp("**Dr. Khalid**") == "*Dr. Khalid*"


def test_the_real_world_appointment_message():
    src = ("Your upcoming appointment is with **Dr. Khalid Al‑Otaibi** for a "
           "**General Consultation** on **Sunday, 31 May 2026 at 10:00 AM**.")
    out = to_whatsapp(src)
    assert "**" not in out
    assert "*Dr. Khalid Al-Otaibi*" in out          # bold single-starred + hyphen fixed
    assert "*General Consultation*" in out
    assert "‑" not in out                            # non-breaking hyphen normalised


def test_headings_become_bold_lines():
    assert to_whatsapp("### Services") == "*Services*"
    assert to_whatsapp("# Title") == "*Title*"


def test_underscore_bold_becomes_single_star():
    assert to_whatsapp("__urgent__") == "*urgent*"


def test_markdown_links_flattened():
    assert to_whatsapp("[book here](https://x.co)") == "book here (https://x.co)"


def test_plain_text_untouched():
    assert to_whatsapp("Hello, how can I help?") == "Hello, how can I help?"


def test_empty_is_safe():
    assert to_whatsapp("") == ""
