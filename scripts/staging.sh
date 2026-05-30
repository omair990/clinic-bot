#!/usr/bin/env bash
# Local staging database — mirrors production so migrations/refactors (e.g. the
# Phase 3b tenant-isolation rewrite) can be tested before they touch prod.
#
# Requires a local Postgres (Homebrew: `brew services start postgresql@16`).
#
# Usage:
#   scripts/staging.sh init           # (re)create clinic_staging + apply schema/seed
#   scripts/staging.sh run <cmd...>   # run any command with staging env loaded
#   scripts/staging.sh test           # run pytest against staging
#   scripts/staging.sh psql           # open psql on the staging DB
set -euo pipefail

DB="clinic_staging"
# Exported BEFORE app.config runs; python-dotenv won't override already-set env vars,
# so this wins over the .env DATABASE_URL.
export DATABASE_URL="postgresql://$(whoami)@localhost:5432/${DB}"
export WA_ACCESS_TOKEN="${WA_ACCESS_TOKEN:-stage-token}"
export WA_PHONE_NUMBER_ID="${WA_PHONE_NUMBER_ID:-stage-pn}"
export WA_VERIFY_TOKEN="${WA_VERIFY_TOKEN:-stage-verify}"
export GEMINI_API_KEY="${GEMINI_API_KEY:-x}"
export USAGE_ENFORCEMENT="${USAGE_ENFORCEMENT:-true}"

cmd="${1:-help}"; shift || true
case "$cmd" in
  init)
    dropdb --if-exists "$DB"
    createdb "$DB"
    python -c "from app.db import init_db, close_db; init_db(); close_db(); print('staging migrated')"
    ;;
  run)  exec "$@" ;;
  test) exec python -m pytest "$@" ;;
  psql) exec psql "$DATABASE_URL" ;;
  *) echo "usage: scripts/staging.sh {init|run <cmd>|test|psql}"; exit 1 ;;
esac
