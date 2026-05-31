"""Text-to-speech (ElevenLabs) for spoken WhatsApp replies.

Off unless an API key is set AND voice replies are enabled (globally or per clinic) —
TTS bills per character. ``build_tts_request`` is pure (unit-tested); ``synthesize``
performs the HTTP call. Output defaults to OGG/Opus so WhatsApp renders a push-to-talk
voice note rather than a generic audio clip.
"""
import logging

import httpx

from app.config import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_TTS_FORMAT,
    ELEVENLABS_TTS_MODEL,
    ELEVENLABS_VOICE_ID,
    LLM_TIMEOUT_S,
)

log = logging.getLogger(__name__)

# our short name -> (ElevenLabs output_format, WhatsApp mime type)
_FORMATS = {
    "opus": ("opus_48000_64", "audio/ogg"),
    "mp3": ("mp3_44100_128", "audio/mpeg"),
}


def available() -> bool:
    return bool(ELEVENLABS_API_KEY)


def build_tts_request(text: str, *, voice_id: str | None = None, model: str | None = None,
                      fmt: str | None = None) -> tuple[str, dict, dict, str]:
    """Return (url, headers, json_payload, output_mime) — pure, no network."""
    voice = voice_id or ELEVENLABS_VOICE_ID
    output_format, mime = _FORMATS.get(fmt or ELEVENLABS_TTS_FORMAT, _FORMATS["opus"])
    url = (f"https://api.elevenlabs.io/v1/text-to-speech/{voice}"
           f"?output_format={output_format}")
    headers = {"xi-api-key": ELEVENLABS_API_KEY, "Accept": "audio/*",
               "Content-Type": "application/json"}
    payload = {"text": text, "model_id": model or ELEVENLABS_TTS_MODEL}
    return url, headers, payload, mime


def synthesize(text: str, *, voice_id: str | None = None, model: str | None = None,
               fmt: str | None = None) -> tuple[bytes, str]:
    """Synthesize speech; returns (audio_bytes, mime). Raises on failure (caller falls
    back to text). Synchronous — call via asyncio.to_thread from async code."""
    url, headers, payload, mime = build_tts_request(text, voice_id=voice_id, model=model, fmt=fmt)
    with httpx.Client(timeout=LLM_TIMEOUT_S) as client:
        r = client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        return r.content, mime
