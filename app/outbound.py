"""Outbound webhook publisher — fires events to n8n/Zapier/etc."""
import logging

import httpx

log = logging.getLogger(__name__)


async def post_event(url: str, payload: dict, timeout: float = 10.0) -> None:
    """Post a JSON payload to an external webhook. Failures are logged, not raised."""
    if not url:
        return
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, json=payload)
            if r.status_code >= 400:
                log.warning("Outbound webhook %s -> %s: %s", url, r.status_code, r.text[:200])
    except httpx.HTTPError as e:
        log.warning("Outbound webhook %s failed: %s", url, e)
