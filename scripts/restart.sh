#!/bin/bash

################################################################################
# Restart Script
# Restart platform services
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

Restart platform services.

SERVICES:
    all              Restart all services (default)
    db               PostgreSQL database
    api              FastAPI server
    watcher          Package watcher
    worker_container Container worker (includes daemon monitor)
    docker-proxy     Docker socket proxy
    runner           Agent runner (if enabled)
    local_watcher    Local watcher process (host)

OPTIONS:
    --hard           Force restart (kill and restart immediately)
    --graceful       Graceful restart (default - 30s shutdown timeout)
    --timeout N      Custom shutdown timeout in seconds
    --no-deps        Don't restart dependencies
    --rebuild        Rebuild images before restarting
    --no-color       Disable colored output
    --help           Show this help message

EXAMPLES:
    $0                      # Restart all services
    $0 api                  # Restart API gracefully
    $0 local_watcher        # Restart local watcher process
    $0 worker_container     # Restart worker with daemon monitor
    $0 db --hard            # Force restart database
    $0 api --rebuild        # Rebuild and restart API

EOF
    exit 0
}

# Parse arguments
SERVICE="all"
HARD=false
GRACEFUL=true
TIMEOUT=30
NO_DEPS=false
REBUILD=false

# Check if first arg is a service
if [[ $# -gt 0 ]] && ! [[ $1 =~ ^- ]]; then
    SERVICE=$1
    shift
fi

while [[ $# -gt 0 ]]; do
    case $1 in
        --hard)
            HARD=true
            GRACEFUL=false
            shift
            ;;
        --graceful)
            HARD=false
            GRACEFUL=true
            shift
            ;;
        --timeout)
            TIMEOUT=$2
            shift 2
            ;;
        --no-deps)
            NO_DEPS=true
            shift
            ;;
        --rebuild)
            REBUILD=true
            shift
            ;;
        --no-color)
            RED=''
            GREEN=''
            YELLOW=''
            BLUE=''
            CYAN=''
            NC=''
            shift
            ;;
        --help)
            usage
            ;;
        *)
            log_error "Unknown option: $1"
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

log_info "Restarting crucibleaiagents platform services..."
echo

# Handle local_watcher specially (not a docker-compose service)
if [ "$SERVICE" = "local_watcher" ]; then
    log_info "Restarting local watcher process..."
    bash "$SCRIPT_DIR/run_local_watcher.sh" restart
    echo
    exit 0
fi

# Handle "all" to include local_watcher
if [ "$SERVICE" = "all" ]; then
    # Check if local watcher is running
    if [ -f "$PROJECT_ROOT/.local_watcher.pid" ]; then
        log_info "Also restarting local watcher..."
        bash "$SCRIPT_DIR/run_local_watcher.sh" restart || true
        echo
    fi
fi

# Verify service exists (if not "all" and not local_watcher)
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

# Rebuild if requested
if [ "$REBUILD" = true ]; then
    if [ "$SERVICE" = "all" ]; then
        log_info "Rebuilding all images..."
        docker-compose build --no-cache
    else
        log_info "Rebuilding image for $SERVICE..."
        docker-compose build --no-cache "$SERVICE"
    fi
    log_success "Build complete"
    echo
fi

# Show what we're doing
if [ "$SERVICE" = "all" ]; then
    if [ "$HARD" = true ]; then
        log_warn "Force restarting ALL services (no graceful shutdown)"
    else
        log_info "Gracefully restarting ALL services (timeout: ${TIMEOUT}s)"
    fi
else
    if [ "$HARD" = true ]; then
        log_warn "Force restarting service: $SERVICE (no graceful shutdown)"
    else
        log_info "Gracefully restarting service: $SERVICE (timeout: ${TIMEOUT}s)"
    fi
fi
echo

# Build restart command
if [ "$HARD" = true ]; then
    # Hard restart (kill immediately)
    if [ "$SERVICE" = "all" ]; then
        log_info "Stopping services..."
        docker-compose kill
        log_info "Starting services..."
        docker-compose up -d
    else
        log_info "Stopping $SERVICE..."
        docker-compose kill "$SERVICE"
        log_info "Starting $SERVICE..."
        docker-compose up -d "$SERVICE"
    fi
else
    # Graceful restart
    if [ "$SERVICE" = "all" ]; then
        log_info "Stopping services (timeout: ${TIMEOUT}s)..."
        docker-compose stop --timeout="$TIMEOUT"
        log_info "Starting services..."
        docker-compose up -d
    else
        log_info "Stopping $SERVICE (timeout: ${TIMEOUT}s)..."
        docker-compose stop --timeout="$TIMEOUT" "$SERVICE"
        log_info "Starting $SERVICE..."
        docker-compose up -d "$SERVICE"
    fi
fi

echo
log_success "Restart complete!"
echo

# Wait for services to be ready
if [ "$SERVICE" = "api" ] || [ "$SERVICE" = "all" ]; then
    log_info "Waiting for API to be ready..."
    max_attempts=30
    attempt=0
    while [ $attempt -lt $max_attempts ]; do
        if curl -sf http://localhost:8080/health &>/dev/null; then
            log_success "API is ready"
            break
        fi
        attempt=$((attempt + 1))
        if [ $attempt -eq $max_attempts ]; then
            log_warn "API didn't respond within ${max_attempts}s"
            break
        fi
        echo -n "."
        sleep 1
    done
    echo
fi

if [ "$SERVICE" = "db" ] || [ "$SERVICE" = "all" ]; then
    log_info "Waiting for database to be ready..."
    max_attempts=30
    attempt=0
    while [ $attempt -lt $max_attempts ]; do
        if docker-compose exec -T db pg_isready -U ${POSTGRES_USER:-admin} -d ${POSTGRES_DB:-crucibleaiagents} &>/dev/null; then
            log_success "Database is ready"
            break
        fi
        attempt=$((attempt + 1))
        if [ $attempt -eq $max_attempts ]; then
            log_warn "Database didn't respond within ${max_attempts}s"
            break
        fi
        echo -n "."
        sleep 1
    done
    echo
fi

echo

# Show service status
if [ "$SERVICE" = "all" ]; then
    log_info "Current service status:"
    docker-compose ps
else
    log_info "Status of $SERVICE:"
    docker-compose ps "$SERVICE"
fi

echo
cat << EOF
${CYAN}Helpful Commands:${NC}
  Check status:   ./scripts/status.sh
  View logs:      ./scripts/logs.sh [$SERVICE]
  Stop platform:  ./scripts/stop.sh

EOF
