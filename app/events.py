import asyncio
import json
import logging
from typing import Any

log = logging.getLogger(__name__)

_subscribers: set[asyncio.Queue] = set()


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    _subscribers.discard(q)


def publish(event_type: str, data: dict[str, Any]) -> None:
    """Fan out an event to all SSE subscribers. Drops if a subscriber's queue is full."""
    payload = json.dumps({"type": event_type, **data}, default=str)
    for q in list(_subscribers):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            log.warning("SSE subscriber queue full, dropping event")
