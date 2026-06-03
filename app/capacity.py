"""Live Anthropic rate-limit probe for the capacity dashboard.

Reads the real per-account limits (requests/min, input-TPM, output-TPM) from Anthropic's
`anthropic-ratelimit-*` response headers via a tiny 1-token call, cached so the dashboard
never hammers the API. Isolated from the agent hot path on purpose — a probe failure just
falls back to the editable defaults in the UI.
"""
import logging
import threading
import time

log = logging.getLogger(__name__)

_TTL_S = 300                       # re-probe at most every 5 min
_lock = threading.Lock()
_cache: dict = {"at": 0.0, "limits": None}


def _gi(headers, key: str):
    v = headers.get(key)
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _probe() -> dict | None:
    """One minimal call; return the account's current Claude rate limits, or None."""
    try:
        from app.providers.claude import _client
        from app.config import CLAUDE_MODEL
        if _client is None:
            return None
        resp = _client.messages.with_raw_response.create(
            model=CLAUDE_MODEL, max_tokens=1,
            messages=[{"role": "user", "content": "ping"}])
        h = resp.headers
        return {
            "model": CLAUDE_MODEL,
            "requests_per_min": _gi(h, "anthropic-ratelimit-requests-limit"),
            "input_tpm": _gi(h, "anthropic-ratelimit-input-tokens-limit"),
            "output_tpm": _gi(h, "anthropic-ratelimit-output-tokens-limit"),
        }
    except Exception:  # noqa: BLE001 — probe must never raise into the endpoint
        log.warning("Anthropic rate-limit probe failed", exc_info=True)
        return None


def rate_limits(force: bool = False) -> dict | None:
    """Cached live Claude rate limits (requests/min, input-TPM, output-TPM), or None."""
    now = time.monotonic()
    with _lock:
        cached = _cache["limits"]
        fresh = cached is not None and (now - _cache["at"]) < _TTL_S
    if fresh and not force:
        return cached
    limits = _probe()
    if limits:
        with _lock:
            _cache["at"] = time.monotonic()
            _cache["limits"] = limits
        return limits
    return cached            # stale-but-better-than-nothing on a failed re-probe
