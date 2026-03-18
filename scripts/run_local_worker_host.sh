#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

if [[ -f "$ROOT_DIR/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.venv/bin/activate"
fi

DB_USER_VAL="${DB_USER:-${POSTGRES_USER:-admin}}"
DB_PASSWORD_VAL="${DB_PASSWORD:-${POSTGRES_PASSWORD:-secret123}}"
DB_NAME_VAL="${DB_NAME:-${POSTGRES_DB:-crucibleaiagents}}"
DB_HOST_VAL="${DB_HOST:-localhost}"
DB_PORT_VAL="${DB_PORT:-5432}"

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://${DB_USER_VAL}:${DB_PASSWORD_VAL}@${DB_HOST_VAL}:${DB_PORT_VAL}/${DB_NAME_VAL}}"
export POLL_SECONDS="${POLL_SECONDS:-3}"

cd "$ROOT_DIR"
exec python worker/local_worker.py
