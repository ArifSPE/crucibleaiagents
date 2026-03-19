#!/bin/bash

################################################################################
# Logs Script
# View and follow logs from platform services
################################################################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'
CYAN=$'\033[0;36m'
NC=$'\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[✗]${NC} $*"
}

# Usage
usage() {
    cat << EOF
Usage: $0 [SERVICE] [OPTIONS]

View and follow logs from platform services.

SERVICES:
    all              All local log files (default)
    api              API log file
    watcher          Watcher log file
    worker_container Worker log file
    worker           Alias for worker_container
    runner           Runner log file
    frontend         Frontend log file
    local_worker     Local worker host process log file
    local_watcher    Local watcher host process log file
    db               Docker logs fallback
    docker-proxy     Docker logs fallback

OPTIONS:
    -f, --follow    Follow log output (default)
    -n, --lines N   Show last N lines (default: 50)
    --no-follow     Don't follow logs (show and exit)
    --tail N        Alias for --lines
    --timestamps    Show timestamps (added by docker-compose)
    --no-color      Disable colored output
    --help          Show this help message

EXAMPLES:
    $0                      # Follow all local log files
    $0 api                  # Follow API log file
    $0 worker_container     # Follow worker log file
    $0 local_worker -n 100  # Show last 100 lines of local worker log
    $0 --no-follow -n 50    # Show last 50 lines and exit
    $0 db --timestamps      # Docker fallback logs with timestamps

FILTERS:
    daemon.monitor          Show daemon monitor events
    ERROR                   Show only ERROR lines
    worker.daemon           Show daemon-related worker events
    local_watcher           Show local watcher events

EXAMPLES WITH FILTERS:
    $0 | grep daemon.monitor               # Daemon monitor lines
    $0 local_watcher | grep -i error      # Local watcher errors
    $0 worker_container | grep -i error   # Worker errors
    $0 all | grep "worker.daemon"         # All daemon events

EOF
    exit 0
}

# Parse arguments
SERVICE="all"
FOLLOW=true
LINES=50
TIMESTAMPS=false
NO_COLOR=false
LOG_DIR="$PROJECT_ROOT/logs"

# Check if first arg is a service
if [[ $# -gt 0 ]] && ! [[ $1 =~ ^- ]]; then
    SERVICE=$1
    shift
fi

while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--follow)
            FOLLOW=true
            shift
            ;;
        -n|--lines|--tail)
            LINES=$2
            shift 2
            ;;
        --no-follow)
            FOLLOW=false
            shift
            ;;
        --timestamps)
            TIMESTAMPS=true
            shift
            ;;
        --no-color)
            RED=''
            GREEN=''
            YELLOW=''
            BLUE=''
            CYAN=''
            NC=''
            NO_COLOR=true
            shift
            ;;
        --help)
            usage
            ;;
        *)
            log_error "Unknown option: $1"
            echo
            usage
            ;;
    esac
done

cd "$PROJECT_ROOT"

get_log_file_for_service() {
    case "$1" in
        api)
            echo "$LOG_DIR/api.log"
            ;;
        watcher)
            echo "$LOG_DIR/watcher.log"
            ;;
        worker|worker_container)
            echo "$LOG_DIR/worker.log"
            ;;
        runner)
            echo "$LOG_DIR/runner.log"
            ;;
        frontend)
            echo "$LOG_DIR/frontend.log"
            ;;
        local_worker)
            echo "$LOG_DIR/local_worker.log"
            ;;
        local_watcher)
            echo "$LOG_DIR/local_watcher.log"
            ;;
        *)
            echo ""
            ;;
    esac
}

tail_one_file() {
    local file="$1"
    local service_name="$2"
    if [ ! -f "$file" ]; then
        log_error "Log file not found for $service_name: $file"
        return 1
    fi

    if [ "$FOLLOW" = true ]; then
        log_info "Following $service_name log: $file"
        echo
        tail -n "$LINES" -f "$file"
    else
        log_info "Showing last $LINES lines from $service_name: $file"
        echo
        tail -n "$LINES" "$file"
    fi
}

tail_all_files() {
    local files=()
    local candidates=(
        "$LOG_DIR/api.log"
        "$LOG_DIR/watcher.log"
        "$LOG_DIR/worker.log"
        "$LOG_DIR/runner.log"
        "$LOG_DIR/frontend.log"
        "$LOG_DIR/local_worker.log"
        "$LOG_DIR/local_watcher.log"
    )

    for candidate in "${candidates[@]}"; do
        if [ -f "$candidate" ]; then
            files+=("$candidate")
        fi
    done

    if [ ${#files[@]} -eq 0 ]; then
        log_error "No local log files found in $LOG_DIR"
        log_info "Start services first (./scripts/start.sh) and local worker/watcher if needed"
        return 1
    fi

    if [ "$FOLLOW" = true ]; then
        log_info "Following all local logs under $LOG_DIR"
        echo
        tail -n "$LINES" -f "${files[@]}"
    else
        log_info "Showing last $LINES lines for all local logs"
        echo
        tail -n "$LINES" "${files[@]}"
    fi
}

if [ "$SERVICE" = "all" ]; then
    tail_all_files
    exit $?
fi

local_log_file="$(get_log_file_for_service "$SERVICE")"
if [ -n "$local_log_file" ]; then
    tail_one_file "$local_log_file" "$SERVICE"
    exit $?
fi

# Fallback: for services not redirected to local files, use docker-compose logs.
if ! command -v docker-compose &> /dev/null; then
    log_error "docker-compose not found"
    exit 1
fi

if ! docker-compose config --services | grep -q "^${SERVICE}$"; then
    log_error "Service '$SERVICE' not found"
    echo
    log_info "Local-file services: api, watcher, worker_container, runner, frontend, local_worker, local_watcher"
    log_info "Compose services:"
    docker-compose config --services | sed 's/^/  - /'
    exit 1
fi

logs_cmd="docker-compose logs --tail=$LINES"
if [ "$FOLLOW" = true ]; then
    logs_cmd="$logs_cmd -f"
fi
if [ "$TIMESTAMPS" = true ]; then
    logs_cmd="$logs_cmd -t"
fi
if [ "$NO_COLOR" = true ]; then
    logs_cmd="$logs_cmd --no-color"
fi

log_info "Service '$SERVICE' uses docker-compose logs fallback"
echo
$logs_cmd "$SERVICE"
