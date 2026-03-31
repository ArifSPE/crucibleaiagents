#!/usr/bin/env bash

# Start API + Frontend locally (without Docker)
# Usage: ./scripts/start_local_api_frontend.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_ROOT/logs"
API_LOG="$LOG_DIR/api-local.log"
FRONTEND_LOG="$LOG_DIR/frontend-local.log"

API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8080}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'
NC=$'\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_ok() { echo -e "${GREEN}[✓]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_err() { echo -e "${RED}[✗]${NC} $*"; }

require_cmd() {
    local cmd="$1"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        log_err "Missing command: $cmd"
        exit 1
    fi
}

cd "$PROJECT_ROOT"
mkdir -p "$LOG_DIR"

require_cmd npm

PYTHON_BIN="python"
if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
fi

if ! "$PYTHON_BIN" -c "import uvicorn" >/dev/null 2>&1; then
    log_err "uvicorn is not available in $PYTHON_BIN"
    log_info "Install backend deps first: $PYTHON_BIN -m pip install -r requirements.txt"
    exit 1
fi

if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/.env"
    set +a
fi

if [[ ! -d "$PROJECT_ROOT/frontend/node_modules" ]]; then
    log_info "Installing frontend dependencies..."
    (cd "$PROJECT_ROOT/frontend" && npm install)
fi

if lsof -iTCP:"$API_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    log_warn "Port $API_PORT is already in use; API may fail to start"
fi

if lsof -iTCP:"$FRONTEND_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    log_warn "Port $FRONTEND_PORT is already in use; frontend may fail to start"
fi

log_info "Starting API locally on http://localhost:$API_PORT"
(
    cd "$PROJECT_ROOT/api"
    exec "$PYTHON_BIN" -m uvicorn main:app --host "$API_HOST" --port "$API_PORT" --reload
) >> "$API_LOG" 2>&1 &
API_PID=$!

sleep 2
if ! kill -0 "$API_PID" >/dev/null 2>&1; then
    log_err "API failed to start. Check $API_LOG"
    exit 1
fi
log_ok "API started (PID: $API_PID)"

log_info "Starting frontend locally on http://localhost:$FRONTEND_PORT"
(
    cd "$PROJECT_ROOT/frontend"
    export VITE_API_BASE_URL="http://localhost:$API_PORT"
    exec npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
) >> "$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!

sleep 2
if ! kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    log_err "Frontend failed to start. Check $FRONTEND_LOG"
    kill "$API_PID" >/dev/null 2>&1 || true
    exit 1
fi

echo "$API_PID" > "$PROJECT_ROOT/.local_api.pid"
echo "$FRONTEND_PID" > "$PROJECT_ROOT/.local_frontend.pid"

log_ok "Frontend started (PID: $FRONTEND_PID)"
echo
log_ok "Local API + Frontend are running"
log_info "API:      http://localhost:$API_PORT"
log_info "Frontend: http://localhost:$FRONTEND_PORT"
log_info "Logs:     $API_LOG and $FRONTEND_LOG"
log_info "PIDs:     .local_api.pid and .local_frontend.pid"
