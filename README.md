# Clinic AI Assistant

A production WhatsApp **AI agent** for a clinic. It holds real conversations (typed
**or voice notes**), looks up pricing and doctors, checks live availability, and
**books / reschedules / cancels appointments end-to-end** — backed by Postgres, with a
staff dashboard. Replies in the patient's own language. No spreadsheets, no external
automation tools.

Voice notes are transcribed with Gemini (`app/transcribe.py`); replies are sent as text
in the same language the patient used, formatted for WhatsApp (`app/formatting.py`).

## How it works

```
WhatsApp Cloud API  (text or voice note)
      │  (webhook, HMAC-verified; voice → Gemini transcription)
      ▼
FastAPI  ──►  Agent loop  ──►  LLM (Gemini ▸ OpenRouter ▸ Claude ▸ Groq ▸ DeepSeek ▸ self-hosted)
                  │  tools                              (tool-calling, circuit-breaker fallback)
                  ▼
   list_services · list_doctors · check_availability
   book_appointment · get_my_appointments
   reschedule_appointment · cancel_appointment · escalate_to_human
                  │
                  ▼
             Postgres  ◄──  Admin dashboard (live feed, appointment management)
```

The model is a true **agent**: it decides which tools to call and loops (model ⇄ tools)
until it has a natural-language answer. It never invents free slots — availability is
computed from each doctor's working hours minus existing bookings, and bookings are
written under a transaction that prevents double-booking. Medical emergencies and
anything out of scope are escalated to staff via WhatsApp.

### Key modules

| File | Responsibility |
|------|----------------|
| `app/agent.py` | The model⇄tool loop (provider-agnostic) |
| `app/tools.py` | Tool specs + handlers + per-turn `AgentContext` |
| `app/scheduling.py` | Slot generation / availability (pure, unit-tested) |
| `app/llm.py` | Neutral message/tool types + multi-provider fallback |
| `app/providers/` | `claude` (Anthropic tool use + prompt caching), `gemini` (manual function calling), `groq`/`deepseek`/`openrouter`/`selfhosted` (OpenAI-compatible) |
| `app/prompts.py` | System prompt (rebuilt per turn with current clinic time) |
| `app/db.py` | Postgres pool + repository functions |
| `app/webhook.py` | WhatsApp verify, signature check, message routing |
| `app/admin.py` | Auth'd dashboard: conversations, appointments, live SSE feed |
| `app/clinic_data.json` | Clinic config: services, doctors, hours, FAQs |

## Local development

Requires Docker (for Postgres) or a local Postgres.

```bash
cp .env.example .env          # fill in WhatsApp + at least GEMINI_API_KEY
docker compose up --build     # app on :8000, postgres on :5432
```

Without Docker:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql://user:pass@localhost:5432/clinic
uvicorn main:app --reload
```

Health check: `GET /` → `{"status":"ok","db":true}`.
Dashboard: `http://localhost:8000/admin/` (password = `ADMIN_PASSWORD`).

## Tests

```bash
pip install pytest
pytest -q          # scheduling logic (no DB/network needed)
```

## Deployment (Railway)

1. Add a **Postgres** plugin — Railway injects `DATABASE_URL` automatically.
2. Set env vars: `WA_ACCESS_TOKEN`, `WA_PHONE_NUMBER_ID`, `WA_VERIFY_TOKEN`,
   `WA_APP_SECRET`, `GEMINI_API_KEY` (+ optional `GROQ_API_KEY`, `DEEPSEEK_API_KEY`),
   `ADMIN_WA_NUMBER`, `ADMIN_PASSWORD`, `SECRET_KEY`.
3. Deploy. The schema is created on startup; the health check path is `/`.
4. Point your Meta WhatsApp webhook at `https://<your-app>/webhook` using `WA_VERIFY_TOKEN`.

> **Gotcha — leave the Railway "Custom Start Command" empty.** This is a Dockerfile
> deployment, so the container start command must come from the Dockerfile's `CMD`
> (`sh -c "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"`), which shell-expands
> `$PORT`. If you set a Custom Start Command in the Railway dashboard, Railway runs it in
> **exec form** — `$PORT` is passed as the literal string `$PORT` instead of the port
> number, uvicorn fails to bind, and the service crash-loops (health check times out,
> hitting `restartPolicyMaxRetries`). Fix: Service → Settings → Deploy → clear **Custom
> Start Command** and redeploy.
>
> As a safety net, the image installs a small `uvicorn` shim (`docker/uvicorn-port-shim`)
> ahead of the real binary in `PATH` that expands a literal `$PORT` before delegating to
> uvicorn — so the container boots even if that dashboard command is set. Clearing the
> command is still the clean fix; the shim is just insurance.

## Configuration notes

- **`AI_PROVIDERS`** sets the fallback order (default `gemini,openrouter,claude,groq,deepseek`).
  A provider listed without its API key is skipped at startup. Each call walks the chain;
  a provider that fails repeatedly trips a circuit breaker and is skipped for a cooldown
  (`LLM_BREAKER_THRESHOLD` / `LLM_BREAKER_COOLDOWN_S`), while a rate-limited (429) provider
  stays in rotation. `LLM_TIMEOUT_S` bounds each call. Set `CLAUDE_MODEL` /
  `OPENROUTER_MODEL` to choose models (`openai/gpt-4o-mini` by default for OpenRouter).
- **`WA_APP_SECRET`** must be set in production — inbound webhooks are rejected if the
  HMAC signature is invalid.
- **`CLINIC_TIMEZONE`** (default `Asia/Riyadh`) governs all slot math and display.
- Clinic services, doctors, hours, and FAQs live in `app/clinic_data.json` — edit there.
