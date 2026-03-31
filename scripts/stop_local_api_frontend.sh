#!/usr/bin/env bash

# Stop API + Frontend started locally (without Docker)
# Usage: ./scripts/stop_local_api_frontend.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

API_PORT="${API_PORT:-8080}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

API_PID_FILE="$PROJECT_ROOT/.local_api.pid"
FRONTEND_PID_FILE="$PROJECT_ROOT/.local_frontend.pid"

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'
NC=$'\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_ok() { echo -e "${GREEN}[✓]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_err() { echo -e "${RED}[✗]${NC} $*"; }

stop_by_pid_file() {
    local pid_file="$1"
    local name="$2"

    if [[ ! -f "$pid_file" ]]; then
        return 1
    fi

    local pid
    pid=$(cat "$pid_file" 2>/dev/null || echo "")
    rm -f "$pid_file"

    if [[ -z "$pid" ]]; then
        return 1
    fi

    if kill -0 "$pid" >/dev/null 2>&1; then
        log_info "Stopping $name (PID: $pid)..."
        kill "$pid" >/dev/null 2>&1 || true
        sleep 1
        if kill -0 "$pid" >/dev/null 2>&1; then
            kill -9 "$pid" >/dev/null 2>&1 || true
        fi
        log_ok "$name stopped"
        return 0
    fi

    return 1
}

stop_by_port() {
    local port="$1"
    local name="$2"
    local pids
    pids=$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)

    if [[ -z "$pids" ]]; then
        return 1
    fi

    log_warn "No PID file process found for $name; stopping listener(s) on port $port: $pids"
    # shellcheck disable=SC2086
    kill $pids >/dev/null 2>&1 || true
    sleep 1
    for pid in $pids; do
        if kill -0 "$pid" >/dev/null 2>&1; then
            kill -9 "$pid" >/dev/null 2>&1 || true
        fi
    done
    log_ok "$name listener(s) stopped on port $port"
    return 0
}

cd "$PROJECT_ROOT"

stopped_any=false

if stop_by_pid_file "$API_PID_FILE" "API"; then
    stopped_any=true
elif stop_by_port "$API_PORT" "API"; then
    stopped_any=true
else
    log_info "API is not running on port $API_PORT"
fi

if stop_by_pid_file "$FRONTEND_PID_FILE" "Frontend"; then
    stopped_any=true
elif stop_by_port "$FRONTEND_PORT" "Frontend"; then
    stopped_any=true
else
    log_info "Frontend is not running on port $FRONTEND_PORT"
fi

if [[ "$stopped_any" = true ]]; then
    log_ok "Local API + frontend stop completed"
else
    log_info "Nothing to stop"
fi
