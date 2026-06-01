"""In-process event bus for the real-time admin console.

Two kinds of traffic flow over the same bus:
  * live activity — ``publish("message"|"typing"|"stoptyping", ...)`` mirrors what is
    happening on WhatsApp so the dashboard's live feed and KPIs update instantly.
  * staff notifications — ``notify(...)`` raises an operator-facing alert (handover,
    new booking, new review, an operational incident) that the notification bell shows
    and toasts.

Subscribers are per-SSE-connection ``asyncio.Queue``s. The newest notifications are also
kept in a small ring buffer so the bell can render history the moment a client connects,
without a dedicated table.

Thread-safety: many producers (``incidents.record``, the agent's ``record_review``) run
inside ``asyncio.to_thread`` worker threads. ``asyncio.Queue`` is not thread-safe, so all
fan-out is marshalled back onto the main event loop via ``call_soon_threadsafe`` whenever
it is invoked off-loop. Call :func:`set_loop` once at startup so we know which loop that is.
"""
import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from itertools import count
from typing import Any

log = logging.getLogger(__name__)

_subscribers: set[asyncio.Queue] = set()
_recent: deque = deque(maxlen=200)
_loop: asyncio.AbstractEventLoop | None = None
_ids = count(1)


def set_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Record the main event loop so off-thread producers can deliver safely."""
    global _loop
    _loop = loop


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    _subscribers.discard(q)


def _deliver(event: dict[str, Any]) -> None:
    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            log.warning("SSE subscriber queue full, dropping %s event", event.get("type"))


def _emit(event: dict[str, Any]) -> None:
    """Fan out to subscribers, hopping onto the event loop if called from a worker thread."""
    loop = _loop
    if loop is None:
        _deliver(event)
        return
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is loop:
        _deliver(event)
    else:
        try:
            loop.call_soon_threadsafe(_deliver, event)
        except RuntimeError:  # loop closed during shutdown
            pass


def publish(event_type: str, data: dict[str, Any]) -> None:
    """Emit a live-activity event (message/typing/stoptyping) to all subscribers."""
    _emit({"type": event_type, "seq": next(_ids), **data})


def notify(title: str, body: str = "", *, level: str = "info", category: str = "general",
           tenant_id: int | None = None, link: str | None = None,
           wa_user: str | None = None) -> dict:
    """Raise a staff-facing notification: buffered for history and pushed to live clients.

    level: "info" | "success" | "warning" | "error" (maps to the bell/toast severity).
    link:  in-app SPA path the bell entry deep-links to (e.g. "/conversations/<wa>").
    """
    note = {
        "type": "notification",
        "id": next(_ids),
        "level": level,
        "title": title,
        "body": (body or "")[:500],
        "category": category,
        "tenant_id": tenant_id,
        "link": link,
        "wa_user": wa_user,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    _recent.append(note)
    _emit(note)
    return note


def recent(scope: int | None = None, limit: int = 50) -> list[dict]:
    """Newest-first recent notifications, filtered to a clinic scope when given.

    A clinic sees its own (tenant_id == scope) plus platform-wide ones (tenant_id None);
    the super-admin (scope None) sees everything.
    """
    items = list(_recent)
    if scope is not None:
        items = [n for n in items if n.get("tenant_id") in (None, scope)]
    return items[-limit:][::-1]
