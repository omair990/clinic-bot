import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.admin import router as admin_router
from app.api import router as api_router
from app.config import (
    COMMIT_SHA,
    EVENT_RETENTION_DAYS,
    INSIGHTS_DIGEST_ENABLED,
    INSIGHTS_DIGEST_INTERVAL_MIN,
    MAINTENANCE_INTERVAL_HOURS,
    NO_SHOW_ENABLED,
    NO_SHOW_SWEEP_INTERVAL_MIN,
    PORT,
    PROCESSED_MSG_RETENTION_HOURS,
    PROVIDER_MONITOR_ENABLED,
    PROVIDER_MONITOR_INTERVAL_MIN,
    SECRET_KEY,
)
from app.db import close_db, init_db, ping, prune_processed_messages, prune_resolved_events
from app.insights import run_digests
from app.no_show import sweep as no_show_sweep
from app.webhook import router as webhook_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
log = logging.getLogger("main")


async def _maintenance_loop() -> None:
    """Periodically prune old dedup rows and old resolved issues."""
    while True:
        try:
            msgs = await asyncio.to_thread(prune_processed_messages, PROCESSED_MSG_RETENTION_HOURS)
            events = await asyncio.to_thread(prune_resolved_events, EVENT_RETENTION_DAYS)
            if msgs or events:
                log.info("maintenance: pruned %s processed messages, %s resolved issues",
                         msgs, events)
        except Exception:  # noqa: BLE001
            log.exception("maintenance prune failed")
        await asyncio.sleep(MAINTENANCE_INTERVAL_HOURS * 3600)


async def _no_show_loop() -> None:
    """Periodically detect no-shows, run recovery outreach, and score upcoming
    appointments for no-show risk (see app/no_show.py)."""
    while True:
        try:
            await no_show_sweep()
        except Exception:  # noqa: BLE001 — a bad pass must not kill the loop
            log.exception("no-show sweep failed")
        await asyncio.sleep(NO_SHOW_SWEEP_INTERVAL_MIN * 60)


async def _insights_digest_loop() -> None:
    """Periodically send due daily/weekly insight digests to clinic owners
    (see app/insights.run_digests). The runner is idempotent per day."""
    while True:
        try:
            await run_digests()
        except Exception:  # noqa: BLE001
            log.exception("insights digest run failed")
        await asyncio.sleep(INSIGHTS_DIGEST_INTERVAL_MIN * 60)


async def _provider_monitor_loop() -> None:
    """Periodically check the primary LLM provider's health and alert staff if it has been
    down for a sustained period (e.g. Claude credits exhausted — see app/provider_monitor.py)."""
    from app import provider_monitor
    while True:
        await asyncio.sleep(PROVIDER_MONITOR_INTERVAL_MIN * 60)   # check after a grace period
        try:
            await provider_monitor.check()
        except Exception:  # noqa: BLE001 — a bad check must not kill the loop
            log.exception("provider monitor failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    tasks = [asyncio.create_task(_maintenance_loop())]
    if NO_SHOW_ENABLED:
        tasks.append(asyncio.create_task(_no_show_loop()))
    if INSIGHTS_DIGEST_ENABLED:
        tasks.append(asyncio.create_task(_insights_digest_loop()))
    if PROVIDER_MONITOR_ENABLED:
        tasks.append(asyncio.create_task(_provider_monitor_loop()))
    yield
    for task in tasks:
        task.cancel()
    close_db()


app = FastAPI(title="Clinic AI Assistant", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=60 * 60 * 24 * 7)


@app.get("/")
def health() -> JSONResponse:
    db_ok = ping()
    return JSONResponse(
        {"status": "ok" if db_ok else "degraded", "db": db_ok, "version": COMMIT_SHA},
        status_code=200 if db_ok else 503,
    )


app.include_router(webhook_router)
app.include_router(api_router)      # JSON API for the React console (/api/*)
app.include_router(admin_router)    # legacy Jinja admin (removed once the SPA reaches parity)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
