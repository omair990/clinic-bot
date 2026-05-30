"""Tests for voice-note transcription (no network — the Gemini client is faked)."""
import pytest

import app.transcribe as t


def test_raises_when_no_key(monkeypatch):
    monkeypatch.setattr(t, "_client", None)
    with pytest.raises(RuntimeError):
        t.transcribe_audio(b"x", "audio/ogg")


def test_strips_codec_suffix_and_returns_text(monkeypatch):
    seen = {}

    class FakeModels:
        def generate_content(self, model, contents, config=None):
            seen["model"] = model
            seen["mime"] = contents[0].inline_data.mime_type
            return type("R", (), {"text": "  Hello there  "})()

    monkeypatch.setattr(t, "_client", type("C", (), {"models": FakeModels()})())
    out = t.transcribe_audio(b"audio-bytes", "audio/ogg; codecs=opus")
    assert out == "Hello there"               # trimmed
    assert seen["mime"] == "audio/ogg"        # codec suffix stripped
    assert seen["model"] == t.TRANSCRIBE_MODEL
