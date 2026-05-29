import logging

import uvicorn
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.admin import router as admin_router
from app.config import PORT, SECRET_KEY
from app.db import init_db
from app.webhook import router as webhook_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)

app = FastAPI(title="Clinic WhatsApp Assistant")

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=60 * 60 * 24 * 7)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/")
def health() -> dict:
    return {"status": "ok"}


app.include_router(webhook_router)
app.include_router(admin_router)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
