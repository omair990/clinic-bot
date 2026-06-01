# --- Stage 1: build the React console (Vite → static bundle) ---
FROM node:20-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci || npm install
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Python app (serves the API, webhook, and the built console) ---
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# ffmpeg: transcode WhatsApp ogg/opus voice notes to wav for transcription
# backends that require wav/mp3 (e.g. OpenRouter audio chat models).
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Built React console from stage 1 (served at /console by FastAPI).
COPY --from=frontend /fe/dist ./frontend/dist

# Install a uvicorn shim ahead of the real binary in PATH. It expands a literal
# "$PORT" arg (which Railway exec-form start commands pass through unexpanded)
# before delegating to the real uvicorn, so the container boots even if a
# dashboard "Custom Start Command" is set. See README "Gotcha".
RUN install -m 0755 docker/uvicorn-port-shim /usr/local/sbin/uvicorn
ENV PATH="/usr/local/sbin:${PATH}"

EXPOSE 8000

# Honour Railway/Heroku-provided $PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
