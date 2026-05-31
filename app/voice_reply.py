"""Spoken replies: mirror the patient's modality (voice in → voice out).

Decides whether to speak, synthesizes via ElevenLabs TTS, and sends a WhatsApp voice
note — falling back to text on any failure so the patient always gets the answer. Gated
hard because TTS costs per character: requires the key, the feature flag (global or
per-clinic ``clinic_data.voice.enabled``), a voice inbound, and a reply under the length
cap. The ``should_speak`` decision is pure and unit-tested.
"""
import asyncio
import logging

from app import tts
from app.config import VOICE_REPLY_ENABLED, VOICE_REPLY_MAX_CHARS
from app.wa_client import send_audio

log = logging.getLogger(__name__)


def _voice_cfg(tenant: dict | None) -> dict:
    return ((tenant or {}).get("clinic_data") or {}).get("voice") or {}


def should_speak(tenant: dict | None, *, inbound_is_voice: bool, text: str) -> bool:
    """Speak only when: the patient sent voice, TTS is configured, the feature is enabled
    (per-clinic value overrides the global default), and the reply fits the length cap."""
    if not inbound_is_voice or not (text or "").strip() or not tts.available():
        return False
    cfg = _voice_cfg(tenant)
    if not cfg.get("enabled", VOICE_REPLY_ENABLED):
        return False
    return len(text) <= VOICE_REPLY_MAX_CHARS


async def maybe_send(to: str, text: str, tenant: dict | None, creds: dict, *,
                     inbound_is_voice: bool) -> bool:
    """Send a spoken reply if appropriate. Returns True if a voice note went out;
    False means the caller should send the text reply instead."""
    if not should_speak(tenant, inbound_is_voice=inbound_is_voice, text=text):
        return False
    cfg = _voice_cfg(tenant)
    try:
        audio, mime = await asyncio.to_thread(
            tts.synthesize, text, voice_id=cfg.get("voice_id") or None)
        await send_audio(to, audio, mime, **creds)
        log.info("Voice reply sent to %s (%d chars, %s)", to, len(text), mime)
        return True
    except Exception as e:  # noqa: BLE001 — any failure degrades to text, never drops the reply
        log.warning("Voice reply to %s failed, falling back to text: %s", to, str(e)[:160])
        return False
