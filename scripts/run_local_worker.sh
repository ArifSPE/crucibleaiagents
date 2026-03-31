#!/bin/bash

# Local Worker - Run local worker as host process
# This script manages the local worker process (not in docker)
# Usage: ./scripts/run_local_worker.sh [start|stop|status|restart|logs]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
WORKER_PID_FILE="$PROJECT_ROOT/.local_worker.pid"
WORKER_LOG_FILE="$PROJECT_ROOT/logs/local_worker.log"

# Color codes
RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'
NC=$'\033[0m' # No Color

# Parse color flag
NO_COLOR=false
for arg in "$@"; do
    if [ "$arg" = "--no-color" ]; then
        NO_COLOR=true
    fi
done

if [ "$NO_COLOR" = true ]; then
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    NC=''
fi

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[!]${NC} $1"
}

is_worker_running() {
    if [ ! -f "$WORKER_PID_FILE" ]; then
        return 1
    fi

    local pid
    pid=$(cat "$WORKER_PID_FILE" 2>/dev/null || echo "")
    if [ -z "$pid" ]; then
        return 1
    fi

    if kill -0 "$pid" 2>/dev/null; then
        return 0
    fi

    rm -f "$WORKER_PID_FILE"
    return 1
}

start_worker() {
    log_info "Starting local worker..."

    if is_worker_running; then
        log_warn "Local worker is already running (PID: $(cat "$WORKER_PID_FILE"))"
        return 0
    fi

    mkdir -p "$PROJECT_ROOT/logs"

    nohup bash "$SCRIPT_DIR/run_local_worker_host.sh" >/dev/null 2>&1 &
    local pid=$!
    echo "$pid" > "$WORKER_PID_FILE"
    sleep 1

    if kill -0 "$pid" 2>/dev/null; then
        log_success "Local worker started (PID: $pid)"
        log_info "Logs: $WORKER_LOG_FILE"
        return 0
    fi

    rm -f "$WORKER_PID_FILE"
    log_error "Failed to confirm local worker startup"
    log_info "Check logs: $WORKER_LOG_FILE"
    return 1
}

stop_worker() {
    log_info "Stopping local worker..."

    if ! is_worker_running; then
        log_warn "Local worker is not running"
        rm -f "$WORKER_PID_FILE"
        return 0
    fi

    local pid
    pid=$(cat "$WORKER_PID_FILE")
    log_info "Sending SIGTERM to PID $pid..."

    if kill -TERM "$pid" 2>/dev/null; then
        local count=0
        while kill -0 "$pid" 2>/dev/null && [ $count -lt 10 ]; do
            sleep 1
            count=$((count + 1))
        done

        if kill -0 "$pid" 2>/dev/null; then
            log_warn "Graceful shutdown timeout, force killing local worker..."
            kill -9 "$pid" 2>/dev/null || true
        fi
    fi

    rm -f "$WORKER_PID_FILE"
    log_success "Local worker stopped"
}

get_status() {
    if is_worker_running; then
        local pid
        pid=$(cat "$WORKER_PID_FILE")
        log_success "Local worker is RUNNING (PID: $pid)"
        ps -p "$pid" -o pid,vsz,rss,lstart,etime,comm 2>/dev/null | tail -1 || true

        if [ -f "$WORKER_LOG_FILE" ]; then
            echo ""
            log_info "Recent logs:"
            tail -5 "$WORKER_LOG_FILE" | sed 's/^/  /'
        fi
        return 0
    fi

    log_error "Local worker is NOT RUNNING"
    if [ -f "$WORKER_LOG_FILE" ]; then
        log_info "Last log entries:"
        tail -5 "$WORKER_LOG_FILE" | sed 's/^/  /'
    fi
    return 1
}

show_logs() {
    local follow=false
    local lines=50

    local args=("$@")
    local i=0
    while [ $i -lt ${#args[@]} ]; do
        case "${args[$i]}" in
            -f|--follow)
                follow=true
                ;;
            -n)
                i=$((i + 1))
                if [ $i -ge ${#args[@]} ]; then
                    log_error "Missing value for -n"
                    return 1
                fi
                lines="${args[$i]}"
                if ! [[ "$lines" =~ ^[0-9]+$ ]]; then
                    log_error "Invalid line count: $lines"
                    return 1
                fi
                ;;
        esac
        i=$((i + 1))
    done

    if [ ! -f "$WORKER_LOG_FILE" ]; then
        log_error "Log file not found: $WORKER_LOG_FILE"
        log_info "Start the worker first: $0 start"
        return 1
    fi

    if [ "$follow" = true ]; then
        log_info "Following logs (Ctrl+C to stop)..."
        tail -f "$WORKER_LOG_FILE"
    else
        log_info "Recent logs (last $lines lines):"
        tail -n "$lines" "$WORKER_LOG_FILE"
    fi
}

restart_worker() {
    log_info "Restarting local worker..."
    stop_worker
    sleep 1
    start_worker
    log_success "Local worker restarted"
}

show_help() {
    cat <<EOF
Local Worker Manager

Usage: $0 [COMMAND] [OPTIONS]

Commands:
    start               Start the local worker process
    stop                Stop the local worker process
    status              Check if worker is running
    restart             Restart the worker
    logs                Show worker logs

Options:
    -f, --follow        Follow logs in real-time (with 'logs' command)
    -n N                Show last N lines (with 'logs' command, default: 50)
    --no-color          Disable colored output
    -h, --help          Show this help

Examples:
    # Start worker
    $0 start

    # Check status
    $0 status

    # Follow logs
    $0 logs -f

    # Restart worker
    $0 restart
EOF
}

COMMAND="${1:-help}"
if [ $# -gt 0 ]; then
    shift
fi

case "$COMMAND" in
    start)
        start_worker
        ;;
    stop)
        stop_worker
        ;;
    status)
        get_status
        ;;
    restart)
        restart_worker
        ;;
    logs)
        show_logs "$@"
        ;;
    -h|--help|help)
        show_help
        ;;
    *)
        log_error "Unknown command: $COMMAND"
        echo ""
        show_help
        exit 1
        ;;
esac