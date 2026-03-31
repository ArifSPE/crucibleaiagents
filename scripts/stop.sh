#!/bin/bash

################################################################################
# Stop Platform Script
# Gracefully stops crucibleaiagents platform services
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

Gracefully stop the crucibleaiagents platform.

OPTIONS:
    --force         Force stop without graceful shutdown (kill -9)
    --remove        Remove containers after stopping (default: keep containers)
    --volumes       Also remove volumes (BE CAREFUL - data loss!)
    --no-color      Disable colored output
    --help          Show this help message

EXAMPLES:
    $0                  # Graceful stop, keep containers
    $0 --remove         # Stop and remove containers
    $0 --force --remove # Force stop and remove containers (fastest)

EOF
    exit 0
}

# Parse arguments
FORCE=false
REMOVE=false
VOLUMES=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --force)
            FORCE=true
            shift
            ;;
        --remove)
            REMOVE=true
            shift
            ;;
        --volumes)
            VOLUMES=true
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

log_info "Stopping crucibleaiagents platform..."
echo

# Check docker-compose
if ! command -v docker-compose &> /dev/null; then
    log_error "docker-compose not found"
    exit 1
fi

# Check if any services are running
services_running=false
performed_actions=false
if docker-compose ps --services --filter "status=running" | grep -q .; then
    services_running=true
else
    log_warn "No running docker-compose services found"
fi

echo

# Show running services
if [ "$services_running" = true ]; then
    log_info "Running services:"
    docker-compose ps --filter "status=running"
    echo
fi

if [ "$FORCE" = true ]; then
    log_warn "Force stopping services (timeout: immediate)..."
    timeout_flag="--timeout=0"
else
    log_info "Gracefully stopping services (timeout: 30 seconds)..."
    timeout_flag="--timeout=30"
fi

# Build stop/down command
cmd=""
if [ "$REMOVE" = true ] || [ "$VOLUMES" = true ]; then
    cmd="docker-compose down $timeout_flag --remove-orphans"
    if [ "$VOLUMES" = true ]; then
        cmd="$cmd -v"
        log_warn "Will also remove volumes - data may be lost!"
        echo
    fi
else
    cmd="docker-compose stop $timeout_flag"
fi

# Stop local watcher if running
if [ -f "$PROJECT_ROOT/.local_watcher.pid" ]; then
    log_info "Stopping local watcher..."
    bash "$SCRIPT_DIR/run_local_watcher.sh" stop
    performed_actions=true
    echo
fi

# Stop local worker if running
if [ -f "$PROJECT_ROOT/.local_worker.pid" ]; then
    log_info "Stopping local worker..."

    bash "$SCRIPT_DIR/run_local_worker.sh" stop
    performed_actions=true
    echo
fi

# Stop/remove detached daemon runtime containers.
# Use both network and name-prefix filters because stale containers may be in Created state
# and not attached to the daemon network yet.
daemon_container_ids="$(
    {
        docker ps -aq --filter "network=crucibleaiagents-daemon"
        docker ps -aq --filter "name=^daemon-pkg"
        docker ps -aq --filter "name=^agent-run"
    } | awk 'NF {print}' | sort -u
)"

if [ -n "$daemon_container_ids" ]; then
    log_info "Stopping detached daemon runtime containers..."
    # shellcheck disable=SC2086
    docker rm -f $daemon_container_ids >/dev/null 2>&1 || true
    log_success "Detached daemon runtime containers removed"
    performed_actions=true
    echo
fi

# Stop services
should_execute_cmd=false
if [ "$services_running" = true ] || [ "$REMOVE" = true ] || [ "$VOLUMES" = true ]; then
    should_execute_cmd=true
fi

if [ "$should_execute_cmd" = true ]; then
    echo
    log_info "Executing: $cmd"
    $cmd
    performed_actions=true
fi

echo
log_success "Platform stopped successfully!"
echo

# If volumes were removed, alert user
if [ "$VOLUMES" = true ]; then
    log_warn "Volumes have been removed!"
fi

# Best-effort daemon network cleanup after detached daemon containers are removed
if docker network inspect crucibleaiagents-daemon >/dev/null 2>&1; then
    if docker network rm crucibleaiagents-daemon >/dev/null 2>&1; then
        log_success "Daemon network removed"
    fi
fi

# If nothing was running and no extra cleanup was needed.
if [ "$performed_actions" = false ]; then
    cat << EOF
${BLUE}Nothing to stop${NC}
Platform services were already stopped.

EOF
# If containers were kept, show cleanup option
elif [ "$REMOVE" = false ] && [ "$VOLUMES" = false ]; then
    cat << EOF
${BLUE}Running containers preserved${NC}
You can:
  - Start again:  ./scripts/start.sh
  - Remove them:  ./scripts/stop.sh --remove
  - View logs:    docker-compose logs

EOF
else
    cat << EOF
${BLUE}All containers removed${NC}
To start again: ./scripts/start.sh

EOF
fi
