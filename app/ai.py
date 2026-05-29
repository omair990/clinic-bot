import importlib
import logging
import time

from app.config import AI_PROVIDERS
from app.schema import AIResponse

log = logging.getLogger(__name__)

_provider_modules = []
for name in AI_PROVIDERS:
    try:
        _provider_modules.append(importlib.import_module(f"app.providers.{name}"))
    except Exception as e:
        log.error("Failed to load provider %s: %s", name, e)

if not _provider_modules:
    raise RuntimeError("No AI providers configured. Set AI_PROVIDERS in .env")

log.info("AI providers loaded: %s", [p.NAME for p in _provider_modules])


def process_message(user_message: str, history: list[dict]) -> AIResponse:
    """Try each provider in order. On transient failure, fall back to the next.
    Within a single provider, retry transient errors up to 2 times with backoff."""
    last_err: BaseException | None = None

    for provider in _provider_modules:
        for attempt in range(2):
            try:
                return provider.call(user_message, history)
            except Exception as e:
                last_err = e
                if provider.is_transient(e):
                    if attempt == 0:
                        log.warning("[%s] transient %s — retrying once", provider.NAME, type(e).__name__)
                        time.sleep(1.5)
                        continue
                    log.warning("[%s] still failing after retry — falling back", provider.NAME)
                    break
                # Non-transient: don't retry, but try next provider
                log.error("[%s] failed: %s", provider.NAME, e)
                break

    raise last_err if last_err else RuntimeError("All providers failed")
