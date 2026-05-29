import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.admin import router as admin_router
from app.config import PORT, SECRET_KEY
from app.db import close_db, init_db, ping
from app.webhook import router as webhook_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield
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
