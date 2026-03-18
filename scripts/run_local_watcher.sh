#!/bin/bash

# Local Watcher - Run package watcher as local process on host
# This script manages the local watcher process (not in docker)
# Usage: ./scripts/run_local_watcher.sh [start|stop|status|restart|logs]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_PATH="$PROJECT_ROOT/.venv"
WATCHER_PID_FILE="$PROJECT_ROOT/.local_watcher.pid"
WATCHER_LOG_FILE="$PROJECT_ROOT/logs/local_watcher.log"

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

# Helper functions
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

# Check if venv exists
check_venv() {
    if [ ! -d "$VENV_PATH" ]; then
        log_error "Virtual environment not found at $VENV_PATH"
        echo "Please run: python -m venv .venv"
        exit 1
    fi
}

# Check if watcher is running
is_watcher_running() {
    if [ ! -f "$WATCHER_PID_FILE" ]; then
        return 1
    fi
    
    local pid=$(cat "$WATCHER_PID_FILE" 2>/dev/null || echo "")
    if [ -z "$pid" ]; then
        return 1
    fi
    
    if kill -0 "$pid" 2>/dev/null; then
        return 0
    else
        # PID file exists but process is gone
        rm -f "$WATCHER_PID_FILE"
        return 1
    fi
}

# Start local watcher
start_watcher() {
    log_info "Starting local watcher..."
    check_venv
    
    if is_watcher_running; then
        log_warn "Local watcher is already running (PID: $(cat "$WATCHER_PID_FILE"))"
        return 0
    fi
    
    # Create logs directory
    mkdir -p "$PROJECT_ROOT/logs"
    
    # Spawn background process
    (
        source "$VENV_PATH/bin/activate"
        cd "$PROJECT_ROOT/watcher"
        python package_watcher.py >> "$WATCHER_LOG_FILE" 2>&1
    ) &
    
    local pid=$!
    echo "$pid" > "$WATCHER_PID_FILE"
    
    log_success "Local watcher started (PID: $pid)"
    log_info "Logs: $WATCHER_LOG_FILE"
}

# Stop local watcher
stop_watcher() {
    log_info "Stopping local watcher..."
    
    if ! is_watcher_running; then
        log_warn "Local watcher is not running"
        rm -f "$WATCHER_PID_FILE"
        return 0
    fi
    
    local pid=$(cat "$WATCHER_PID_FILE")
    log_info "Sending SIGTERM to PID $pid..."
    
    if kill -TERM "$pid" 2>/dev/null; then
        # Wait up to 10 seconds for graceful shutdown
        local count=0
        while kill -0 "$pid" 2>/dev/null && [ $count -lt 10 ]; do
            sleep 1
            count=$((count + 1))
        done
        
        # If still running, force kill
        if kill -0 "$pid" 2>/dev/null; then
            log_warn "Graceful shutdown timeout, force killing..."
            kill -9 "$pid" 2>/dev/null || true
        fi
    fi
    
    rm -f "$WATCHER_PID_FILE"
    log_success "Local watcher stopped"
}

# Get watcher status
get_status() {
    if is_watcher_running; then
        local pid=$(cat "$WATCHER_PID_FILE")
        log_success "Local watcher is RUNNING (PID: $pid)"
        
        # Show process info
        ps -p "$pid" -o pid,vsz,rss,lstart,etime,comm 2>/dev/null | tail -1 || true
        
        # Show last 5 lines of log
        if [ -f "$WATCHER_LOG_FILE" ]; then
            echo ""
            log_info "Recent logs:"
            tail -5 "$WATCHER_LOG_FILE" | sed 's/^/  /'
        fi
        return 0
    else
        log_error "Local watcher is NOT RUNNING"
        
        # Show if log file exists
        if [ -f "$WATCHER_LOG_FILE" ]; then
            log_info "Last log entries:"
            tail -5 "$WATCHER_LOG_FILE" | sed 's/^/  /'
        fi
        return 1
    fi
}

# Show logs
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
    
    if [ ! -f "$WATCHER_LOG_FILE" ]; then
        log_error "Log file not found: $WATCHER_LOG_FILE"
        log_info "Start the watcher first: $0 start"
        return 1
    fi
    
    if [ "$follow" = true ]; then
        log_info "Following logs (Ctrl+C to stop)..."
        tail -f "$WATCHER_LOG_FILE"
    else
        log_info "Recent logs (last $lines lines):"
        tail -n "$lines" "$WATCHER_LOG_FILE"
    fi
}

# Restart watcher
restart_watcher() {
    log_info "Restarting local watcher..."
    stop_watcher
    sleep 1
    start_watcher
    log_success "Local watcher restarted"
}

# Show help
show_help() {
    cat <<EOF
Local Watcher Manager

Usage: $0 [COMMAND] [OPTIONS]

Commands:
    start               Start the local watcher process
    stop                Stop the local watcher process
    status              Check if watcher is running
    restart             Restart the watcher
    logs                Show watcher logs
    
Options:
    -f, --follow        Follow logs in real-time (with 'logs' command)
    -n N                Show last N lines (with 'logs' command, default: 50)
    --no-color          Disable colored output
    -h, --help          Show this help

Examples:
    # Start watcher
    $0 start
    
    # Check status
    $0 status
    
    # Follow logs
    $0 logs -f
    
    # Show last 100 lines
    $0 logs -n 100
    
    # Restart
    $0 restart

EOF
}

# Main
case "${1:-}" in
    start)
        start_watcher
        ;;
    stop)
        stop_watcher
        ;;
    status)
        get_status
        ;;
    restart)
        restart_watcher
        ;;
    logs)
        shift || true
        show_logs "$@"
        ;;
    -h|--help|help)
        show_help
        ;;
    *)
        if [ -n "${1:-}" ]; then
            log_error "Unknown command: $1"
            echo ""
        fi
        show_help
        exit 1
        ;;
esac
