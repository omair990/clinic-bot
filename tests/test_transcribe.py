"""Tests for voice-note transcription + fallback chain (no network)."""
import pytest

import app.transcribe as t


def test_raises_when_no_backends(monkeypatch):
    monkeypatch.setattr(t, "_BACKENDS", [])
    with pytest.raises(RuntimeError):
        t.transcribe_audio(b"x", "audio/ogg")


def test_returns_first_success(monkeypatch):
    def good(b, m):
        return "  first  "

    def never(b, m):
        raise AssertionError("second backend should not run")

    monkeypatch.setattr(t, "_BACKENDS", [("gemini", good), ("groq", never)])
    assert t.transcribe_audio(b"x", "audio/ogg") == "first"   # trimmed


def test_falls_back_when_first_errors(monkeypatch):
    def boom(b, m):
        raise RuntimeError("429 quota exhausted")

    def good(b, m):
        return "rescued"

    monkeypatch.setattr(t, "_BACKENDS", [("gemini", boom), ("groq", good)])
    assert t.transcribe_audio(b"x", "audio/ogg") == "rescued"


def test_empty_result_is_not_a_fallback(monkeypatch):
    # Silence -> "" is a valid success, returned without trying the next backend.
    def silent(b, m):
        return ""

    def never(b, m):
        raise AssertionError("should not fall back on empty")

    monkeypatch.setattr(t, "_BACKENDS", [("gemini", silent), ("groq", never)])
    assert t.transcribe_audio(b"x", "audio/ogg") == ""


def test_all_fail_raises_last_error(monkeypatch):
    def boom(b, m):
        raise RuntimeError("nope")

    monkeypatch.setattr(t, "_BACKENDS", [("gemini", boom), ("groq", boom)])
    with pytest.raises(RuntimeError):
        t.transcribe_audio(b"x", "audio/ogg")


def test_openrouter_sends_base64_audio_and_parses_reply(monkeypatch):
    sent = {}
    monkeypatch.setattr(t, "_to_wav", lambda b: b"WAVBYTES")
    monkeypatch.setattr(t, "OPENROUTER_API_KEY", "k")

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "  hello from OR  "}}]}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, json=None):
            sent["url"] = url
            sent["json"] = json
            return FakeResp()

    monkeypatch.setattr(t.httpx, "Client", FakeClient)
    out = t._openrouter(b"oggbytes", "audio/ogg")

    assert out == "hello from OR"
    parts = sent["json"]["messages"][0]["content"]
    assert any(p.get("type") == "input_audio" for p in parts)
    assert "openrouter.ai" in sent["url"]


def test_gemini_strips_codec_from_mime(monkeypatch):
    seen = {}

    class FakeModels:
        def generate_content(self, model, contents, config=None):
            seen["mime"] = contents[0].inline_data.mime_type
            return type("R", (), {"text": "hi"})()

    monkeypatch.setattr(t, "_gemini_client", type("C", (), {"models": FakeModels()})())
    assert t._gemini(b"x", "audio/ogg; codecs=opus") == "hi"
    assert seen["mime"] == "audio/ogg"
