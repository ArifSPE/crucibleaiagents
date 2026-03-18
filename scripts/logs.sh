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
    all             All services (default)
    db              PostgreSQL database
    api             FastAPI server
    watcher         Package watcher (docker)
    worker_container Container worker (includes daemon monitor)
    docker-proxy    Docker socket proxy
    runner          Agent runner (if enabled)
    local_watcher   Local watcher process (host)

OPTIONS:
    -f, --follow    Follow log output (default)
    -n, --lines N   Show last N lines (default: 50)
    --no-follow     Don't follow logs (show and exit)
    --tail N        Alias for --lines
    --timestamps    Show timestamps (added by docker-compose)
    --no-color      Disable colored output
    --help          Show this help message

EXAMPLES:
    $0                     # Follow all logs
    $0 api                 # Follow API logs only
    $0 worker_container    # Follow worker logs
    $0 api -n 100          # Show last 100 lines of API logs
    $0 --no-follow -n 50   # Show last 50 lines and exit
    $0 worker_container --timestamps  # Worker logs with timestamps

FILTERS:
    daemon.monitor         Show daemon monitor events
    ERROR                  Show only ERROR lines
    worker.daemon          Show daemon-related worker events
    local_watcher          Show local watcher events

EXAMPLES WITH FILTERS:
    $0 | grep daemon.monitor              # Docker daemon monitor
    $0 local_watcher | grep -i error     # Local watcher errors
    $0 worker_container | grep -i error  # Worker errors
    $0 all | grep "worker.daemon"        # All daemon events

EOF
    exit 0
}

# Parse arguments
SERVICE="all"
FOLLOW=true
LINES=50
TIMESTAMPS=false
NO_COLOR=false

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

# Check docker-compose
if ! command -v docker-compose &> /dev/null; then
    log_error "docker-compose not found"
    exit 1
fi

# Build logs command
logs_cmd="docker-compose logs"

# Add follow flag
if [ "$FOLLOW" = true ]; then
    logs_cmd="$logs_cmd -f"
fi

# Add lines
logs_cmd="$logs_cmd --tail=$LINES"

# Add timestamps
if [ "$TIMESTAMPS" = true ]; then
    logs_cmd="$logs_cmd -t"
fi

# Add no-color
if [ "$NO_COLOR" = true ]; then
    logs_cmd="$logs_cmd --no-color"
fi

# Handle local_watcher separately (not a docker-compose service)
if [ "$SERVICE" = "local_watcher" ]; then
    local_watcher_log="$PROJECT_ROOT/logs/local_watcher.log"
    if [ ! -f "$local_watcher_log" ]; then
        log_error "Local watcher log file not found: $local_watcher_log"
        log_info "Start local watcher with: ./scripts/run_local_watcher.sh start"
        exit 1
    fi
    
    if [ "$FOLLOW" = true ]; then
        log_info "Following local_watcher logs (press Ctrl+C to exit)"
        echo
        tail -f "$local_watcher_log"
    else
        log_info "Showing last $LINES lines from local_watcher"
        echo
        tail -n "$LINES" "$local_watcher_log"
    fi
    exit 0
fi

# Add service
if [ "$SERVICE" != "all" ]; then
    logs_cmd="$logs_cmd $SERVICE"
fi

# Verify service exists (if not "all")
if [ "$SERVICE" != "all" ]; then
    if ! docker-compose config --services | grep -q "^${SERVICE}$"; then
        log_error "Service '$SERVICE' not found in docker-compose.yml"
        echo
        log_info "Available services:"
        docker-compose config --services | sed 's/^/  - /'
        log_info "Other services:"
        echo "  - local_watcher (host process)"
        echo
        exit 1
    fi
fi

# Show what we're doing
if [ "$SERVICE" != "all" ]; then
    if [ "$FOLLOW" = true ]; then
        log_info "Following logs for service: $SERVICE (press Ctrl+C to exit)"
    else
        log_info "Showing last $LINES lines for service: $SERVICE"
    fi
else
    if [ "$FOLLOW" = true ]; then
        log_info "Following logs for all services (press Ctrl+C to exit)"
    else
        log_info "Showing last $LINES lines for all services"
    fi
fi
echo

# Execute logs command
$logs_cmd

# If not following, show helpful info on exit
if [ "$FOLLOW" = false ]; then
    echo
    log_info "Use './scripts/logs.sh $SERVICE -f' to follow logs"
fi
