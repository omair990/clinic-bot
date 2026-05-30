"""Speech-to-text for WhatsApp voice notes, via Gemini (reuses GEMINI_API_KEY).

Transcription preserves the spoken language (Arabic stays Arabic, English stays
English), so the agent's existing "reply in the same language" rule then answers
voice notes in the caller's language automatically.
"""
import logging

from google import genai
from google.genai import types

from app.config import GEMINI_API_KEY, TRANSCRIBE_MODEL

log = logging.getLogger(__name__)

_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
ENABLED = _client is not None

_PROMPT = (
    "Transcribe the speech in this audio verbatim, in its ORIGINAL language "
    "(Arabic or English). Do not translate. Output ONLY the transcription text — "
    "no quotes, no labels, no commentary. If there is no intelligible speech, output nothing."
)


def transcribe_audio(audio_bytes: bytes, mime_type: str) -> str:
    """Return the transcript of a voice note. Raises if transcription is unavailable."""
    if _client is None:
        raise RuntimeError("Transcription unavailable: GEMINI_API_KEY not set")
    # WhatsApp sends e.g. "audio/ogg; codecs=opus"; Gemini wants the bare type.
    mime = (mime_type or "audio/ogg").split(";")[0].strip()
    resp = _client.models.generate_content(
        model=TRANSCRIBE_MODEL,
        contents=[
            types.Part.from_bytes(data=audio_bytes, mime_type=mime),
            _PROMPT,
        ],
        config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=1000),
    )
    text = (resp.text or "").strip()
    log.info("Transcribed %d bytes (%s) -> %d chars", len(audio_bytes), mime, len(text))
    return text
