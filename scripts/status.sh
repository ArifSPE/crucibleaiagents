#!/bin/bash

################################################################################
# Status Script
# Check health and status of platform services
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

log_status() {
    if [ "$2" = "running" ]; then
        echo -e "${GREEN}✓${NC} $1: running"
    elif [ "$2" = "health" ]; then
        echo -e "${GREEN}✓${NC} $1: running (healthy)"
    elif [ "$2" = "unhealthy" ]; then
        echo -e "${YELLOW}⚠${NC} $1: running (unhealthy)"
    elif [ "$2" = "starting" ]; then
        echo -e "${YELLOW}◐${NC} $1: starting"
    else
        echo -e "${RED}✗${NC} $1: not running"
    fi
}

# Usage
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Check health and status of platform services.

OPTIONS:
    --detailed      Show detailed information (logs, ports, etc.)
    --check-api     Perform API health check
    --check-db      Perform database connection check
    --all           Equivalent to --detailed --check-api --check-db
    --no-color      Disable colored output
    --help          Show this help message

EXAMPLES:
    $0                   # Quick status overview
    $0 --detailed        # Detailed status with container info
    $0 --all             # Full health check (all checks)
    $0 --check-api       # Verify API is responding

EOF
    exit 0
}

# Parse arguments
DETAILED=false
CHECK_API=false
CHECK_DB=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --detailed)
            DETAILED=true
            shift
            ;;
        --check-api)
            CHECK_API=true
            shift
            ;;
        --check-db)
            CHECK_DB=true
            shift
            ;;
        --all)
            DETAILED=true
            CHECK_API=true
            CHECK_DB=true
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

# If the shell inherits the container-specific docker-proxy endpoint, reset it for host checks.
if [[ "${DOCKER_HOST:-}" == tcp://docker-proxy:* ]]; then
    unset DOCKER_HOST
fi

# Check Docker daemon
if ! docker info &> /dev/null; then
    log_error "Docker daemon not running"
    exit 1
fi

echo
log_info "Platform Status Check"
echo

# Get service statuses
echo -e "${CYAN}Service Status:${NC}"
echo

# Resolve service status via container inspect for robust parsing across compose output formats.
get_compose_service_status() {
    local service="$1"
    local container_id
    container_id=$(docker-compose ps -q "$service" 2>/dev/null | head -n 1 || true)

    if [ -z "$container_id" ]; then
        echo "down"
        return
    fi

    local state
    state=$(docker inspect --format '{{.State.Status}}' "$container_id" 2>/dev/null || echo "")

    if [ "$state" != "running" ]; then
        echo "down"
        return
    fi

    local health
    health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$container_id" 2>/dev/null || echo "")

    if [ -z "$health" ]; then
        echo "running"
    elif [ "$health" = "healthy" ]; then
        echo "health"
    elif [ "$health" = "starting" ]; then
        echo "starting"
    else
        echo "unhealthy"
    fi
}

# Check each service
for service in docker-proxy db mcp_server api watcher frontend worker_container; do
    status=$(get_compose_service_status "$service")
    log_status "$service" "$status"
done

echo

# Check for runner service (optional)
if docker-compose config --services 2>/dev/null | grep -q "^runner$"; then
    runner_status=$(get_compose_service_status "runner")
    log_status "runner" "$runner_status"
fi

# Check local watcher process
if [ -f "$PROJECT_ROOT/.local_watcher.pid" ]; then
    local_watcher_pid=$(cat "$PROJECT_ROOT/.local_watcher.pid" 2>/dev/null || echo "")
    if [ -n "$local_watcher_pid" ] && kill -0 "$local_watcher_pid" 2>/dev/null; then
        log_status "local_watcher" "running"
    else
        log_status "local_watcher" "down"
    fi
else
    log_status "local_watcher" "down"
fi

# Check local worker process
if [ -f "$PROJECT_ROOT/.local_worker.pid" ]; then
    if bash "$SCRIPT_DIR/run_local_worker.sh" status --no-color >/dev/null 2>&1; then
        log_status "local_worker" "running"
    else
        log_status "local_worker" "down"
    fi
else
    log_status "local_worker" "down"
fi

echo

# Port Status
echo -e "${CYAN}Service Ports:${NC}"
log_info "API:         http://localhost:8080"
log_info "MCP Server:  http://localhost:${MCP_SERVER_PORT:-9001}${MCP_SERVER_PATH:-/mcp}"
log_info "Database:    postgres://localhost:5432"
log_info "Frontend:    http://localhost:5173 (if enabled)"
echo

# Detailed info if requested
if [ "$DETAILED" = true ]; then
    echo -e "${CYAN}Detailed Status:${NC}"
    echo
    docker-compose ps
    echo
fi

# API Health Check
if [ "$CHECK_API" = true ]; then
    echo -e "${CYAN}API Health Check:${NC}"
    
    if curl -sf http://localhost:8080/health &>/dev/null; then
        log_success "API is responding"
        
        # Try to get health details
        if command -v jq &> /dev/null; then
            api_response=$(curl -s http://localhost:8080/health)
            echo "Response: $api_response" | jq '.' 2>/dev/null || echo "Response: $api_response"
        else
            curl -s http://localhost:8080/health
        fi
    else
        log_error "API is not responding"
        log_info "Try checking logs: ./scripts/logs.sh api"
    fi
    echo
fi

# MCP Health Check (piggybacked with --check-api to keep flags simple)
if [ "$CHECK_API" = true ]; then
    echo -e "${CYAN}MCP Server Health Check:${NC}"
    if docker-compose exec -T mcp_server python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:${MCP_SERVER_PORT:-9001}/health', timeout=2); sys.exit(0)" &>/dev/null; then
        log_success "MCP server is responding"
    else
        log_error "MCP server is not responding"
        log_info "Try checking logs: ./scripts/logs.sh mcp_server"
    fi
    echo
fi

# Database Connection Check
if [ "$CHECK_DB" = true ]; then
    echo -e "${CYAN}Database Connection Check:${NC}"
    
    if docker-compose exec -T db pg_isready -U ${POSTGRES_USER:-admin} -d ${POSTGRES_DB:-crucibleaiagents} &>/dev/null; then
        log_success "Database is accessible"
        
        # Get database stats
        db_stats=$(docker-compose exec -T db psql -U ${POSTGRES_USER:-admin} -d ${POSTGRES_DB:-crucibleaiagents} -c "SELECT datname, pg_size_pretty(pg_database.dattablespace) FROM pg_database;" 2>/dev/null || echo "")
        
        if [ -n "$db_stats" ]; then
            echo "$db_stats"
        fi
    else
        log_error "Database is not accessible"
        log_info "Try checking logs: ./scripts/logs.sh db"
    fi
    echo
fi

# Summary
echo -e "${CYAN}Summary:${NC}"
running_count=$(docker-compose ps --filter "status=running" --services 2>/dev/null | awk 'NF {count++} END {print count+0}')
total_count=$(docker-compose config --services 2>/dev/null | awk 'NF {count++} END {print count+0}')

if [ "$running_count" -eq "$total_count" ] && [ "$total_count" -gt 0 ]; then
    log_success "All services are running ($running_count/$total_count)"
elif [ "$running_count" -gt 0 ]; then
    log_warn "Some services running ($running_count/$total_count)"
else
    log_error "No services running"
    log_info "Start platform: ./scripts/start.sh"
fi

echo

# Helpful commands
if [ "$running_count" -eq 0 ]; then
    cat << EOF
${CYAN}Quick Start:${NC}
  ./scripts/start.sh

EOF
elif [ "$CHECK_API" = false ]; then
    cat << EOF
${CYAN}Helpful Commands:${NC}
  Check logs:      ./scripts/logs.sh [service]
  Full health:     ./scripts/status.sh --all
  Stop platform:   ./scripts/stop.sh
  Restart service: ./scripts/restart.sh [service]

EOF
fi
