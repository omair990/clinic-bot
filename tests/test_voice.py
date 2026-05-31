"""Two-way voice: ElevenLabs Scribe STT backend, TTS synthesis, and the spoken-reply
decision/fallback. Pure unit tests with fakes — no network, no DB."""
import asyncio

from app import transcribe, tts, voice_reply


# --- TTS request shape ---------------------------------------------------------
def test_build_tts_request_opus_is_ogg_voice_note():
    url, headers, payload, mime = tts.build_tts_request("hello", voice_id="V123")
    assert "/text-to-speech/V123" in url and "output_format=opus" in url
    assert mime == "audio/ogg"                       # ogg/opus -> WhatsApp voice note
    assert payload["text"] == "hello" and "model_id" in payload
    assert headers["xi-api-key"] is not None


def test_build_tts_request_mp3_is_audio_clip():
    _u, _h, _p, mime = tts.build_tts_request("hi", fmt="mp3")
    assert mime == "audio/mpeg"


def test_synthesize_returns_audio_bytes_and_mime(monkeypatch):
    class FakeResp:
        content = b"OGGDATA"
        def raise_for_status(self): pass

    class FakeClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, *a, **k): return FakeResp()

    monkeypatch.setattr(tts.httpx, "Client", FakeClient)
    audio, mime = tts.synthesize("hello", voice_id="V")
    assert audio == b"OGGDATA" and mime == "audio/ogg"


# --- Scribe STT backend --------------------------------------------------------
def test_elevenlabs_stt_parses_text_and_keeps_language(monkeypatch):
    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return {"language_code": "ar", "text": "  مرحبا  "}

    class FakeClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, *a, **k): return FakeResp()

    monkeypatch.setattr(transcribe.httpx, "Client", FakeClient)
    monkeypatch.setattr(transcribe, "ELEVENLABS_API_KEY", "k")
    assert transcribe._elevenlabs(b"audio", "audio/ogg; codecs=opus") == "مرحبا"


def test_elevenlabs_is_a_registered_backend():
    assert "elevenlabs" in transcribe._AVAILABLE


# --- should_speak gating -------------------------------------------------------
def _tenant(enabled=None):
    voice = {} if enabled is None else {"enabled": enabled}
    return {"clinic_data": {"voice": voice}}


def test_speaks_only_when_inbound_is_voice(monkeypatch):
    monkeypatch.setattr(voice_reply.tts, "available", lambda: True)
    t = _tenant(enabled=True)
    assert voice_reply.should_speak(t, inbound_is_voice=True, text="hi") is True
    assert voice_reply.should_speak(t, inbound_is_voice=False, text="hi") is False


def test_no_speak_without_tts_configured(monkeypatch):
    monkeypatch.setattr(voice_reply.tts, "available", lambda: False)
    assert voice_reply.should_speak(_tenant(True), inbound_is_voice=True, text="hi") is False


def test_per_clinic_flag_overrides_global(monkeypatch):
    monkeypatch.setattr(voice_reply.tts, "available", lambda: True)
    monkeypatch.setattr(voice_reply, "VOICE_REPLY_ENABLED", False)   # global off
    assert voice_reply.should_speak(_tenant(True), inbound_is_voice=True, text="hi") is True
    assert voice_reply.should_speak(_tenant(False), inbound_is_voice=True, text="hi") is False
    assert voice_reply.should_speak(_tenant(None), inbound_is_voice=True, text="hi") is False  # inherits global


def test_length_cap_blocks_long_replies(monkeypatch):
    monkeypatch.setattr(voice_reply.tts, "available", lambda: True)
    monkeypatch.setattr(voice_reply, "VOICE_REPLY_MAX_CHARS", 10)
    t = _tenant(True)
    assert voice_reply.should_speak(t, inbound_is_voice=True, text="x" * 5) is True
    assert voice_reply.should_speak(t, inbound_is_voice=True, text="x" * 50) is False


# --- maybe_send: speak, fall back, skip ---------------------------------------
def test_maybe_send_speaks_when_enabled(monkeypatch):
    monkeypatch.setattr(voice_reply.tts, "available", lambda: True)
    monkeypatch.setattr(voice_reply, "VOICE_REPLY_ENABLED", True)
    monkeypatch.setattr(voice_reply.tts, "synthesize", lambda text, **k: (b"A", "audio/ogg"))
    sent = {}

    async def fake_send_audio(to, audio, mime, **creds):
        sent.update(to=to, mime=mime)
        return {"ok": 1}
    monkeypatch.setattr(voice_reply, "send_audio", fake_send_audio)

    ok = asyncio.run(voice_reply.maybe_send("966x", "hi", _tenant(True), {}, inbound_is_voice=True))
    assert ok is True and sent["to"] == "966x" and sent["mime"] == "audio/ogg"


def test_maybe_send_falls_back_to_text_on_failure(monkeypatch):
    monkeypatch.setattr(voice_reply.tts, "available", lambda: True)
    monkeypatch.setattr(voice_reply, "VOICE_REPLY_ENABLED", True)
    monkeypatch.setattr(voice_reply.tts, "synthesize", lambda text, **k: (b"A", "audio/ogg"))

    async def boom(*a, **k):
        raise RuntimeError("send failed")
    monkeypatch.setattr(voice_reply, "send_audio", boom)

    ok = asyncio.run(voice_reply.maybe_send("966x", "hi", _tenant(True), {}, inbound_is_voice=True))
    assert ok is False                               # caller will send text instead


def test_maybe_send_skips_text_inbound(monkeypatch):
    monkeypatch.setattr(voice_reply.tts, "available", lambda: True)
    ok = asyncio.run(voice_reply.maybe_send("966x", "hi", _tenant(True), {}, inbound_is_voice=False))
    assert ok is False
