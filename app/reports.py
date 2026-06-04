"""Operations reports for the admin console.

A clinic (or the super-admin, across every clinic) picks a date range and gets a
deterministic summary of what happened — appointments by outcome, no-shows, reviews,
WhatsApp activity, and estimated revenue — that the SPA renders on screen and the user
exports to CSV or PDF.

Pure aggregation over the database: exact, fast, and unit-testable (the tests monkeypatch
the ``db`` functions, no real DB needed). The CSV/PDF rendering lives in the React app; this
module only returns structured JSON. Estimated revenue multiplies each *completed* visit by
the service's configured ``price_sar`` (services without a price contribute nothing), so it
is a best-effort figure, never a billing number.
"""
import logging
from collections import Counter
from datetime import datetime, timedelta

from app import db
from app.config import TIMEZONE, TZ

log = logging.getLogger(__name__)

CURRENCY = "SAR"  # clinic service prices are stored as price_sar
MAX_RANGE_DAYS = 366  # guardrail: a single report never spans more than a year

# Appointment outcomes we summarize (everything the agent/staff can set).
_STATUSES = ("confirmed", "completed", "cancelled", "no_show")


def default_range(now: datetime | None = None) -> tuple[datetime, datetime]:
    """The default window when the UI doesn't pass dates: the last 30 days (inclusive of
    today). Returns timezone-aware [since, until) bounds in the clinic timezone."""
    now = now or datetime.now(TZ)
    until = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return until - timedelta(days=31), until


def parse_range(date_from: str | None, date_to: str | None,
                now: datetime | None = None) -> tuple[datetime, datetime]:
    """Turn ``from``/``to`` ``YYYY-MM-DD`` query params into a half-open [since, until)
    window in the clinic timezone. ``to`` is treated as an inclusive day (so until is the
    start of the day after). Falls back to :func:`default_range` for missing/invalid input
    and clamps the span to :data:`MAX_RANGE_DAYS`."""
    d_since, d_until = default_range(now)
    since = _parse_day(date_from) or d_since
    to_day = _parse_day(date_to)
    until = (to_day + timedelta(days=1)) if to_day else d_until
    if until <= since:                      # swapped or empty → one day
        until = since + timedelta(days=1)
    if (until - since).days > MAX_RANGE_DAYS:
        since = until - timedelta(days=MAX_RANGE_DAYS)
    return since, until


def _parse_day(s: str | None) -> datetime | None:
    """A ``YYYY-MM-DD`` string → midnight (clinic tz), or None if blank/unparseable."""
    s = (s or "").strip()
    if not s:
        return None
    try:
        d = datetime.strptime(s[:10], "%Y-%m-%d")
    except ValueError:
        return None
    return d.replace(tzinfo=TZ)


def _price_map(scope: int | None) -> dict[tuple[int, str], float]:
    """``{(tenant_id, service_name_lower): price}`` from each clinic's configured services.
    One clinic when scoped, every active clinic when the super-admin views all."""
    tenants = [db.get_tenant(scope)] if scope is not None else db.all_active_tenants()
    out: dict[tuple[int, str], float] = {}
    for t in tenants:
        if not t:
            continue
        for s in ((t.get("clinic_data") or {}).get("services") or []):
            if not isinstance(s, dict):
                continue
            name = str(s.get("name") or "").strip().lower()
            price = s.get("price_sar")
            if name and isinstance(price, (int, float)) and not isinstance(price, bool):
                out[(t["id"], name)] = float(price)
    return out


def _appt_row(a: dict, prices: dict[tuple[int, str], float]) -> dict:
    """One serialized appointment line for the report tables/exports."""
    svc = (a.get("service") or "").strip()
    price = prices.get((a["tenant_id"], svc.lower()))
    return {
        "id": a["id"],
        "tenant_id": a["tenant_id"],
        "wa_user": a["wa_user"],
        "patient_name": a.get("patient_name"),
        "doctor": a.get("doctor"),
        "service": a.get("service"),
        "status": a["status"],
        "start_at": a["start_at"].isoformat() if a.get("start_at") else None,
        "price": price,
    }


def _review_stats(rows: list[dict]) -> dict:
    """Avg rating + counts over the reviews actually in the window (range-accurate, unlike
    the all-time db.review_stats)."""
    rated = [r["rating"] for r in rows if r.get("rating") is not None]
    responded = sum(1 for r in rows if r.get("stage") == "done")
    avg = round(sum(rated) / len(rated), 1) if rated else None
    return {"requested": len(rows), "responded": responded,
            "avg_rating": avg, "rated": len(rated)}


def build_report(scope: int | None, since: datetime, until: datetime,
                 tz: str = TIMEZONE) -> dict:
    """The full operations report for [since, until) at clinic ``scope`` (None = all clinics).

    Deterministic; every number comes straight from the database for the window."""
    prices = _price_map(scope)
    appts = db.appointments_in_range(since, until, scope)
    rows = [_appt_row(a, prices) for a in appts]
    by_status = Counter(a["status"] for a in appts)
    total = len(appts)
    completed = by_status.get("completed", 0)
    no_show = by_status.get("no_show", 0)

    revenue = round(sum(r["price"] for r in rows
                        if r["status"] == "completed" and r["price"]), 2)

    msg = db.insight_message_stats(scope, since, until)
    conv = db.insight_conversion(scope, since, until)
    review_rows = db.reviews_in_range(since, until, scope)

    summary = {
        "appointments": total,
        "completed": completed,
        "cancelled": by_status.get("cancelled", 0),
        "no_shows": no_show,
        "confirmed": by_status.get("confirmed", 0),
        "completion_rate": round(completed / total * 100) if total else 0,
        "no_show_rate": round(no_show / total * 100) if total else 0,
        "unique_patients": len({a["wa_user"] for a in appts}),
        "est_revenue": revenue,
        "currency": CURRENCY,
        "messages": msg.get("messages") or 0,
        "inbound": msg.get("inbound") or 0,
        "patients_messaged": conv.get("users_messaged") or 0,
        "patients_booked": conv.get("users_booked") or 0,
        "conversion_pct": conv.get("conversion_pct") or 0,
    }
    return {
        "since": since.isoformat(),
        "until": until.isoformat(),
        "tz": tz,
        "summary": summary,
        "status_breakdown": {s: by_status.get(s, 0) for s in _STATUSES},
        "appointments": rows,
        "no_shows": [r for r in rows if r["status"] == "no_show"],
        "reviews": {"stats": _review_stats(review_rows),
                    "rows": [_review_row(r) for r in review_rows]},
    }


def _review_row(r: dict) -> dict:
    return {
        "id": r["id"],
        "tenant_id": r["tenant_id"],
        "wa_user": r["wa_user"],
        "patient_name": r.get("patient_name"),
        "doctor": r.get("doctor"),
        "service": r.get("service"),
        "rating": r.get("rating"),
        "comment": r.get("comment"),
        "stage": r.get("stage"),
        "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
    }
