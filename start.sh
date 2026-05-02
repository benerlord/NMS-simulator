#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/backend"

if [ -f .env ]; then
  set -a; . ./.env; set +a
fi

: "${APP_HOST:=0.0.0.0}"
: "${APP_PORT:=8080}"

exec python -m app.main
