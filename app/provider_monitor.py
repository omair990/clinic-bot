"""Primary-LLM-provider health monitor.

When the first provider in the chain (normally Claude) keeps failing — e.g. the Anthropic
credit balance is exhausted — the assistant silently degrades onto the fallback chain
(Gemini/Mistral). That can go unnoticed for a long time. This monitor watches the circuit
breaker and, once the primary has been down past a threshold, raises an Issue and pings the
admin over WhatsApp. It alerts ONCE per outage and sends an all-clear when the provider
recovers.
"""
import logging

from app import incidents, llm
from app.config import (
    AI_PROVIDERS,
    LLM_OUTAGE_ALERT_MIN,
)

log = logging.getLogger(__name__)

# Providers we've already alerted about during their CURRENT outage (cleared on recovery).
_alerted: set[str] = set()


async def _notify_admin(text: str) -> None:
    """Best-effort WhatsApp ping to the platform admin number(s). Never raises."""
    try:
        from app import notify  # routes to ADMIN_WA_NUMBER (comma-separated supported)
        await notify.notify_tech(text)
    except Exception:  # noqa: BLE001 — an alert failure must not break the monitor loop
        log.warning("admin alert send failed", exc_info=True)


async def check() -> None:
    """One health check of the primary LLM provider. Idempotent: alerts once per outage."""
    primary = AI_PROVIDERS[0] if AI_PROVIDERS else None
    if not primary:
        return
    outage = llm.provider_outage_seconds(primary)

    # Recovered: the provider answered again since we last alerted → send an all-clear.
    if outage is None:
        if primary in _alerted:
            _alerted.discard(primary)
            log.info("primary provider %s recovered", primary)
            await _notify_admin(f"✅ {primary} is responding again — the assistant is back to "
                                "normal.")
        return

    if outage < LLM_OUTAGE_ALERT_MIN * 60 or primary in _alerted:
        return  # not down long enough yet, or already alerted this outage

    _alerted.add(primary)
    mins = int(outage // 60)
    fallback = ", ".join(AI_PROVIDERS[1:]) or "none"
    msg = (f"⚠️ Assistant degraded: {primary} has been failing for ~{mins} min, so replies are "
           f"running on the fallback chain ({fallback}). If this is the Anthropic credit "
           "balance, top it up to restore normal quality.")
    log.error("provider monitor: %s down ~%dm — alerting admin", primary, mins)
    incidents.record("llm", f"{primary} provider down ~{mins}m (fallback active)",
                     level="error", detail=msg)
    await _notify_admin(msg)
