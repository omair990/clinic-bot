import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.admin import router as admin_router
from app.config import (
    EVENT_RETENTION_DAYS,
    MAINTENANCE_INTERVAL_HOURS,
    PORT,
    PROCESSED_MSG_RETENTION_HOURS,
    SECRET_KEY,
)
from app.db import close_db, init_db, ping, prune_processed_messages, prune_resolved_events
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    task = asyncio.create_task(_maintenance_loop())
    yield
    task.cancel()
    close_db()


app = FastAPI(title="Clinic AI Assistant", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=60 * 60 * 24 * 7)


@app.get("/")
def health() -> JSONResponse:
    db_ok = ping()
    return JSONResponse(
        {"status": "ok" if db_ok else "degraded", "db": db_ok},
        status_code=200 if db_ok else 503,
    )


app.include_router(webhook_router)
app.include_router(admin_router)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
