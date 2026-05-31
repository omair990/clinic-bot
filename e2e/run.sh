#!/usr/bin/env bash
# Self-contained runner for the clinic-editor browser test.
#
# Spins up a throwaway local Postgres DB + the app, seeds a tenant, drives the editor in
# the system Chrome via Playwright, then tears everything down. Production is never touched.
#
# Requires: local Postgres (createdb/dropdb on PATH), the project venv, Node + the system
# Google Chrome, and the app's Python deps. Usage:  bash e2e/run.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${E2E_PORT:-8099}"
DB="${E2E_DB:-clinic_e2e}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-testpass123}"
export SECRET_KEY="${SECRET_KEY:-e2e-local-secret}"
export SECRETS_KEY="${SECRETS_KEY:-bV9k8mZ2pQr5sT7wXy0AbCdEfGhIjKlMnOpQrStUvWx=}"
export DATABASE_URL="postgresql://localhost/${DB}"
export BASE="http://127.0.0.1:${PORT}"
export TENANT_ID=2
export SCREENSHOT="${SCREENSHOT:-}"

APP_PID=""
cleanup() {
  [ -n "$APP_PID" ] && kill "$APP_PID" 2>/dev/null || true
  dropdb "$DB" 2>/dev/null || true
}
trap cleanup EXIT

# Activate venv if present.
[ -f .venv/bin/activate ] && source .venv/bin/activate

echo "==> creating throwaway DB $DB"
dropdb "$DB" 2>/dev/null || true
createdb "$DB"

echo "==> init schema + seed tenant id 2"
python - <<'PY'
from app import db
db.init_db()
db.create_tenant("Test Clinic", "browser-test", None, 1, "Asia/Riyadh", None,
                 {"clinic": {"name": "Seed Clinic"}, "services": [], "doctors": [], "faqs": []})
print("seeded")
PY

echo "==> starting app on :$PORT"
uvicorn main:app --host 127.0.0.1 --port "$PORT" >/tmp/e2e-app.log 2>&1 &
APP_PID=$!
for i in $(seq 1 20); do
  curl -sf "http://127.0.0.1:${PORT}/" >/dev/null 2>&1 && break
  sleep 0.5
done

echo "==> installing playwright (js package only; uses system Chrome)"
( cd e2e && [ -d node_modules/playwright ] || npm install --no-audit --no-fund >/dev/null 2>&1 )

echo "==> driving the editor in Chrome"
node e2e/clinic_editor.spec.js
