"""Safe issue/event recorder — writes operational problems to system_events for the
admin "Issues" page. Recording must NEVER raise or break the request it's reporting on.
"""
import logging

from app import db

log = logging.getLogger(__name__)


def record(category: str, message: str, *, level: str = "error", detail: str | None = None,
           tenant_id: int | None = None, wa_user: str | None = None) -> None:
    try:
        db.record_event(level, category, message, detail=detail,
                        tenant_id=tenant_id, wa_user=wa_user)
    except Exception:  # noqa: BLE001 — observability must not take down the app
        log.warning("failed to record system event (%s: %s)", category, message)
