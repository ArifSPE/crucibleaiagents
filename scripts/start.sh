#!/bin/bash

################################################################################
# Start Platform Script
# Starts crucibleaiagents platform services in correct order with health checks
################################################################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'
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
Usage: $0 [OPTIONS]

Start the crucibleaiagents platform with health checks.

OPTIONS:
    --build [SERVICE...]  Build images before starting (all if none specified)
    --daemon             Run in background (default: attach to logs)
    --local-watcher      Also start local watcher process
    --local-worker       Also start local worker process
    --no-color           Disable colored output
    --help               Show this help message

EXAMPLES:
    $0                              # Start with live logs
    $0 --build --daemon             # Build all images and start in background
    $0 --build api                  # Rebuild only the api image then start
    $0 --build api worker_container # Rebuild specific services then start
    $0 --daemon --local-watcher     # Start with local watcher process
    $0 --daemon --local-worker      # Start with local worker process

EOF
    exit 0
}

# Parse arguments
BUILD=false
BUILD_SERVICES=()
DAEMON=false
LOCAL_WATCHER=false
LOCAL_WORKER=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --build)
            BUILD=true
            shift
            # Collect optional service names that follow --build (stop at next flag)
            while [[ $# -gt 0 && ! "$1" == --* ]]; do
                BUILD_SERVICES+=("$1")
                shift
            done
            ;;
        --daemon)
            DAEMON=true
            shift
            ;;
        --local-watcher)
            LOCAL_WATCHER=true
            shift
            ;;
        --local-worker)
            LOCAL_WORKER=true
            shift
            ;;
        --no-color)
            RED=''
            GREEN=''
            YELLOW=''
            BLUE=''
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

# Ensure local host log directory exists for service log redirection.
mkdir -p "$PROJECT_ROOT/logs"

log_info "Starting crucibleaiagents platform..."
echo

# Load environment
if [ -f .env ]; then
    log_info "Loading environment from .env"
    export $(cat .env | grep -v '^#' | xargs)
else
    log_warn "No .env file found, using defaults"
fi

# Check docker-compose
if ! command -v docker-compose &> /dev/null; then
    log_error "docker-compose not found. Please install Docker Compose."
    exit 1
fi

# Check Docker daemon
if ! docker info &> /dev/null; then
    log_error "Docker daemon not running. Please start Docker."
    exit 1
fi

log_success "Prerequisites checked"
echo

# Build if requested
if [ "$BUILD" = true ]; then
    if [ ${#BUILD_SERVICES[@]} -gt 0 ]; then
        log_info "Building images for: ${BUILD_SERVICES[*]}..."
        docker-compose build --no-cache "${BUILD_SERVICES[@]}" || {
            log_error "Build failed for: ${BUILD_SERVICES[*]}"
            exit 1
        }
        log_success "Images built successfully: ${BUILD_SERVICES[*]}"
    else
        log_info "Building all images..."
        docker-compose build --no-cache || {
            log_error "Build failed"
            exit 1
        }
        log_success "All images built successfully"
    fi
    echo
fi

# Stop existing containers (if any)
log_info "Cleaning up existing containers..."
docker-compose down --remove-orphans 2>/dev/null || true
log_success "Cleanup complete"
echo

# Start services in order
log_info "Starting services..."
echo

# Start docker-proxy first (security layer)
log_info "  → Starting docker-proxy (security layer)..."
docker-compose up -d docker-proxy
sleep 2

# Reconcile daemon network ownership with docker-compose.
# If a stale manually-created network exists, remove it so Compose can recreate with proper labels.
log_info "  → Reconciling daemon network..."
daemon_network_name="crucibleaiagents-daemon"
if docker network inspect "$daemon_network_name" >/dev/null 2>&1; then
    compose_label=$(docker network inspect "$daemon_network_name" --format '{{ index .Labels "com.docker.compose.network" }}' 2>/dev/null || true)

    if [ "$compose_label" != "daemon" ]; then
        log_warn "Found non-compose daemon network; cleaning it up"

        daemon_container_ids=$(docker ps -aq --filter "network=${daemon_network_name}")
        if [ -n "$daemon_container_ids" ]; then
            # shellcheck disable=SC2086
            docker rm -f $daemon_container_ids >/dev/null 2>&1 || true
        fi

        docker network rm "$daemon_network_name" >/dev/null 2>&1 || true
        log_success "Removed stale daemon network"
    else
        log_success "Compose-managed daemon network detected"
    fi
else
    log_success "No existing daemon network found (Compose will create it)"
fi
echo

# Start database
log_info "  → Starting database..."
docker-compose up -d db
sleep 3

# Wait for database to be healthy
log_info "  → Waiting for database health check..."
max_attempts=30
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if docker-compose exec -T db pg_isready -U ${POSTGRES_USER:-admin} -d ${POSTGRES_DB:-crucibleaiagents} &>/dev/null; then
        log_success "Database is healthy"
        break
    fi
    attempt=$((attempt + 1))
    if [ $attempt -eq $max_attempts ]; then
        log_error "Database failed to start within timeout"
        docker-compose logs db
        exit 1
    fi
    echo -n "."
    sleep 1
done
echo

# Start API
log_info "  → Starting API service..."
docker-compose up -d api
sleep 5

# Wait for API to be healthy
log_info "  → Waiting for API health check..."
max_attempts=${API_HEALTH_TIMEOUT_SECONDS:-180}
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if curl -sf http://localhost:8080/health &>/dev/null; then
        log_success "API is healthy"
        break
    fi
    attempt=$((attempt + 1))
    if [ $attempt -eq $max_attempts ]; then
        log_error "API failed to start within timeout"
        docker-compose logs api
        exit 1
    fi
    echo -n "."
    sleep 1
done
echo

# Start watcher
log_info "  → Starting package watcher..."
docker-compose up -d watcher
log_success "Watcher started"
echo

# Start worker_container (includes daemon monitor)
log_info "  → Starting container worker (with daemon monitor)..."
docker-compose up -d worker_container
log_success "Worker started"
echo

# Start local watcher if requested
if [ "$LOCAL_WATCHER" = true ]; then
    log_info "  → Starting local watcher process..."
    if bash "$SCRIPT_DIR/run_local_watcher.sh" start; then
        log_success "Local watcher started"
    else
        log_warn "Failed to start local watcher"
    fi
    echo
fi

# Start local worker if requested
if [ "$LOCAL_WORKER" = true ]; then
    log_info "  → Starting local worker process..."

    if pgrep -af "python .*worker/local_worker.py" >/dev/null 2>&1; then
        log_warn "Local worker is already running"
    else
        local_worker_pid_file="$PROJECT_ROOT/.local_worker.pid"
        nohup bash "$SCRIPT_DIR/run_local_worker_host.sh" >/dev/null 2>&1 &
        local_worker_pid=$!
        echo "$local_worker_pid" > "$local_worker_pid_file"
        sleep 1

        if kill -0 "$local_worker_pid" 2>/dev/null; then
            log_success "Local worker started (PID: $local_worker_pid)"
            log_info "Logs: $PROJECT_ROOT/logs/local_worker.log"
        else
            log_warn "Failed to confirm local worker startup; check logs/local_worker.log"
        fi
    fi
    echo
fi

# Verify all services
log_info "Verifying all services..."
echo

services_running=$(docker-compose ps --services --filter "status=running" | wc -l)
services_total=$(docker-compose config --services | wc -l)

if [ "$services_running" -ge "$services_total" ]; then
    log_success "All services are running"
    echo
    docker-compose ps
else
    log_warn "Some services are not running yet (starting, may need a moment)"
    echo
    docker-compose ps
fi

echo
log_success "Platform started successfully!"
echo

# Summary
cat << EOF
${BLUE}Platform Services:${NC}
  API:               http://localhost:8080
  Frontend:          http://localhost:3000 (if enabled)
  Database:          postgres://localhost:5432

${BLUE}Useful commands:${NC}
  logs:              ./scripts/logs.sh [service]
  status:            ./scripts/status.sh
  stop:              ./scripts/stop.sh
  restart:           ./scripts/restart.sh [service]

${BLUE}Next steps:${NC}
  1. Verify API is responding:  curl http://localhost:8080/health
  2. View logs:                ./scripts/logs.sh
    3. Start local worker:       ./scripts/start.sh --local-worker
  4. Start local watcher:      ./scripts/run_local_watcher.sh start

EOF

# Show logs if not daemon mode
if [ "$DAEMON" = false ]; then
    echo
    log_info "Showing live logs (press Ctrl+C to detach)..."
    echo
    docker-compose logs -f
fi
