# Voice (two-way)

The assistant handles WhatsApp voice both ways: it **transcribes** inbound voice notes
(speech-to-text) and can **reply with a voice note** (text-to-speech). ElevenLabs powers
both, alongside the existing transcription providers.

## Inbound — speech-to-text (`app/transcribe.py`)

A fallback chain set by `TRANSCRIBE_PROVIDERS` (default
`gemini → elevenlabs → groq → openrouter → openai`); each backend is skipped if its key is
missing, tried in order until one succeeds. Transcription preserves the spoken language
(Arabic stays Arabic), so the agent's "reply in the same language" rule answers voice notes
in the caller's language automatically.

- **ElevenLabs Scribe** (`scribe_v1`) is included but placed **after Gemini** — validate its
  Arabic accuracy against the current default before promoting it to primary (reorder via
  `TRANSCRIBE_PROVIDERS`). Needs `ELEVENLABS_API_KEY`.

## Outbound — text-to-speech (`app/tts.py`, `app/voice_reply.py`)

When a patient sends a voice note, we can reply with one (modality mirroring). **Off by
default** — TTS bills per character.

**Gate (all must hold, see `voice_reply.should_speak`):**
1. `ELEVENLABS_API_KEY` is set.
2. The inbound message was a voice note.
3. Voice replies are enabled — `VOICE_REPLY_ENABLED=true` globally, or per clinic via
   `clinic_data.voice.enabled` (the per-clinic value overrides the global default).
4. The reply is within `VOICE_REPLY_MAX_CHARS` (default 600) — longer answers go as text.

**Delivery:** synthesize → upload to WhatsApp (`media_id`) → send as an audio message.
OGG/Opus (`ELEVENLABS_TTS_FORMAT=opus`, the default) renders as a push-to-talk voice note;
`mp3` plays as a generic clip. **Any TTS or send failure falls back to the text reply** — the
patient is never left without an answer (same degrade-don't-drop principle as the LLM and
connector breakers).

Per-clinic voice/model live in a `clinic_data.voice` block (pass-through in the schema, so
it round-trips through the editor):

```json
{ "voice": { "enabled": true, "voice_id": "<ElevenLabs voice id>" } }
```

## Config

| Var | Default | Purpose |
|---|---|---|
| `ELEVENLABS_API_KEY` | — | Enables Scribe STT and TTS (both dormant without it). |
| `ELEVENLABS_STT_MODEL` | `scribe_v1` | Inbound transcription model. |
| `VOICE_REPLY_ENABLED` | `false` | Global on/off for spoken replies. |
| `VOICE_REPLY_MAX_CHARS` | `600` | Replies longer than this go as text (cost/length guard). |
| `ELEVENLABS_TTS_MODEL` | `eleven_multilingual_v2` | TTS model (Arabic + English). |
| `ELEVENLABS_VOICE_ID` | a multilingual default | Default voice; override per clinic. |
| `ELEVENLABS_TTS_FORMAT` | `opus` | `opus` (voice note) or `mp3` (audio clip). |

## Tradeoffs & real-world notes

- **Cost is the main constraint.** TTS is per-character; STT is per-minute. Hence: TTS off by
  default, per-clinic opt-in, a length cap, and voice-only-when-voice (never speak at text
  conversations). Consider caching TTS for repeated/templated messages if volume grows.
- **Quality before primary.** Don't make Scribe the first STT backend until its Arabic
  accuracy is validated against Gemini on real clinic audio.
- **Latency.** TTS adds a couple of seconds; fine for WhatsApp's async UX, and the typing
  indicator already covers the think time.
- **Graceful degrade.** STT failure falls through the chain; TTS failure falls back to text.
  Voice is always an enhancement, never a single point of failure for the reply.
- **Deploying is safe-by-default.** With no `ELEVENLABS_API_KEY` and `VOICE_REPLY_ENABLED`
  unset, behaviour is unchanged — the Scribe backend is skipped and no replies are spoken.

## Tests

`tests/test_voice.py`: TTS request shape (opus→ogg voice note, mp3→clip), `synthesize` via a
fake client, the Scribe backend parse, and the full `should_speak`/`maybe_send` gating matrix
including the text fallback. Live ElevenLabs HTTP is not covered — verify against the real API
with a key (same convention as the connector backends).
