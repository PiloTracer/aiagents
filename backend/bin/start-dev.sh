#!/bin/bash
set -euo pipefail

APP_DIR=${UVICORN_APP_DIR:-/app/app}
HOST=${UVICORN_HOST:-0.0.0.0}
PORT=${UVICORN_PORT:-8000}
RELOAD_DIRS=${UVICORN_RELOAD_DIRS:-$APP_DIR}
WORKERS=${UVICORN_WORKERS:-1}

UVICORN_ARGS=(
  app.main:app
  --host "$HOST"
  --port "$PORT"
  --workers "$WORKERS"
  --proxy-headers
  --reload
  --reload-dir "$RELOAD_DIRS"
)

if [[ -n "${DEBUGPY:-}" && "${DEBUGPY}" != "0" ]]; then
  DEBUG_PORT=${DEBUGPY_PORT:-5678}
  echo "[dev] Starting backend with debugpy on 0.0.0.0:${DEBUG_PORT}" >&2
  exec python -m debugpy --listen 0.0.0.0:${DEBUG_PORT} -m uvicorn "${UVICORN_ARGS[@]}"
else
  echo "[dev] Starting backend with auto-reload" >&2
  exec uvicorn "${UVICORN_ARGS[@]}"
fi
