#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/backend"

if [ -f .env ]; then
  set -a; . ./.env; set +a
fi

: "${APP_HOST:=0.0.0.0}"
: "${APP_PORT:=8080}"

exec python -m uvicorn app.main:app --host "$APP_HOST" --port "$APP_PORT"
