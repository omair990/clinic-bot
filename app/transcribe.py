"""Speech-to-text for WhatsApp voice notes, with a provider fallback chain.

Order is set by TRANSCRIBE_PROVIDERS (default gemini → groq → openai); each backend
is skipped if its key is missing, and tried in turn until one succeeds. Transcription
preserves the spoken language (Arabic stays Arabic, English stays English), so the
agent's "reply in the same language" rule then answers voice notes in the caller's
language automatically.
"""
import base64
import logging
import subprocess

import httpx
from google import genai
from google.genai import types

from app.config import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_STT_MODEL,
    GEMINI_API_KEY,
    GROQ_API_KEY,
    GROQ_WHISPER_MODEL,
    LLM_TIMEOUT_S,
    OPENAI_API_KEY,
    OPENAI_WHISPER_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_TRANSCRIBE_MODEL,
    TRANSCRIBE_MODEL,
    TRANSCRIBE_PROVIDERS,
)

log = logging.getLogger(__name__)

_gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

_PROMPT = (
    "Transcribe the speech in this audio verbatim, in its ORIGINAL language "
    "(Arabic or English). Do not translate. Output ONLY the transcription text — "
    "no quotes, no labels, no commentary. If there is no intelligible speech, output nothing."
)


def _bare_mime(mime_type: str) -> str:
    # WhatsApp sends e.g. "audio/ogg; codecs=opus"; downstream APIs want the bare type.
    return (mime_type or "audio/ogg").split(";")[0].strip()


def _gemini(audio_bytes: bytes, mime_type: str) -> str:
    resp = _gemini_client.models.generate_content(
        model=TRANSCRIBE_MODEL,
        contents=[
            types.Part.from_bytes(data=audio_bytes, mime_type=_bare_mime(mime_type)),
            _PROMPT,
        ],
        config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=1000),
    )
    return (resp.text or "").strip()


def _whisper(endpoint: str, api_key: str, model: str, audio_bytes: bytes, mime_type: str) -> str:
    """OpenAI-compatible /audio/transcriptions (Groq + OpenAI Whisper)."""
    mime = _bare_mime(mime_type)
    ext = mime.split("/")[-1] or "ogg"
    files = {"file": (f"audio.{ext}", audio_bytes, mime)}
    data = {"model": model, "response_format": "text"}
    with httpx.Client(timeout=LLM_TIMEOUT_S) as client:
        r = client.post(endpoint, headers={"Authorization": f"Bearer {api_key}"},
                        files=files, data=data)
        r.raise_for_status()
        return r.text.strip()


def _groq(audio_bytes: bytes, mime_type: str) -> str:
    return _whisper("https://api.groq.com/openai/v1/audio/transcriptions",
                    GROQ_API_KEY, GROQ_WHISPER_MODEL, audio_bytes, mime_type)


def _openai(audio_bytes: bytes, mime_type: str) -> str:
    return _whisper("https://api.openai.com/v1/audio/transcriptions",
                    OPENAI_API_KEY, OPENAI_WHISPER_MODEL, audio_bytes, mime_type)


def _elevenlabs(audio_bytes: bytes, mime_type: str) -> str:
    """ElevenLabs Scribe speech-to-text. Language is auto-detected, so Arabic stays
    Arabic and English stays English (same contract as the other backends)."""
    mime = _bare_mime(mime_type)
    ext = mime.split("/")[-1] or "ogg"
    files = {"file": (f"audio.{ext}", audio_bytes, mime)}
    data = {"model_id": ELEVENLABS_STT_MODEL}
    with httpx.Client(timeout=LLM_TIMEOUT_S) as client:
        r = client.post("https://api.elevenlabs.io/v1/speech-to-text",
                        headers={"xi-api-key": ELEVENLABS_API_KEY}, files=files, data=data)
        r.raise_for_status()
        return (r.json().get("text") or "").strip()


def _to_wav(audio_bytes: bytes) -> bytes:
    """Transcode arbitrary audio (WhatsApp ogg/opus) to 16kHz mono wav via ffmpeg."""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-i", "pipe:0", "-ac", "1", "-ar", "16000", "-f", "wav", "pipe:1"],
        input=audio_bytes, capture_output=True, timeout=30, check=True,
    )
    return proc.stdout


def _openrouter(audio_bytes: bytes, mime_type: str) -> str:
    """OpenRouter has no Whisper endpoint — transcribe via an audio-capable chat
    model. Those accept base64 wav/mp3, so transcode the ogg/opus note first."""
    wav_b64 = base64.b64encode(_to_wav(audio_bytes)).decode()
    payload = {
        "model": OPENROUTER_TRANSCRIBE_MODEL,
        "temperature": 0,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": _PROMPT},
                {"type": "input_audio", "input_audio": {"data": wav_b64, "format": "wav"}},
            ],
        }],
    }
    with httpx.Client(timeout=LLM_TIMEOUT_S) as client:
        r = client.post("https://openrouter.ai/api/v1/chat/completions",
                        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"}, json=payload)
        r.raise_for_status()
        return (r.json()["choices"][0]["message"]["content"] or "").strip()


# name -> (fn, is_configured)
_AVAILABLE = {
    "gemini": (_gemini, bool(_gemini_client)),
    "elevenlabs": (_elevenlabs, bool(ELEVENLABS_API_KEY)),
    "openrouter": (_openrouter, bool(OPENROUTER_API_KEY)),
    "groq": (_groq, bool(GROQ_API_KEY)),
    "openai": (_openai, bool(OPENAI_API_KEY)),
}

_BACKENDS: list = []
for _name in TRANSCRIBE_PROVIDERS:
    _entry = _AVAILABLE.get(_name)
    if not _entry:
        log.warning("Unknown transcription provider %r — skipping", _name)
        continue
    _fn, _ok = _entry
    if not _ok:
        log.info("Transcription provider %s has no key — skipping", _name)
        continue
    _BACKENDS.append((_name, _fn))

ENABLED = bool(_BACKENDS)
if ENABLED:
    log.info("Transcription backends: %s", [n for n, _ in _BACKENDS])


def transcribe_audio(audio_bytes: bytes, mime_type: str) -> str:
    """Transcribe a voice note, walking the fallback chain. Raises if all fail.

    An empty string is a valid result (no intelligible speech) and is returned as-is;
    only exceptions trigger fallback to the next backend.
    """
    if not _BACKENDS:
        raise RuntimeError("Transcription unavailable: no provider configured")
    last_err: BaseException | None = None
    for name, fn in _BACKENDS:
        try:
            text = (fn(audio_bytes, mime_type) or "").strip()
            log.info("[transcribe:%s] %d bytes -> %d chars", name, len(audio_bytes), len(text))
            return text
        except Exception as e:  # noqa: BLE001
            last_err = e
            log.warning("[transcribe:%s] failed: %s", name, str(e)[:160])
    raise last_err if last_err else RuntimeError("All transcription providers failed")
