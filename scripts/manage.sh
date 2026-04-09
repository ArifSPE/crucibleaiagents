#!/bin/bash

################################################################################
# Platform Management Script
# Central hub for platform operations
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
MAGENTA=$'\033[0;35m'
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

# Interactive menu
show_menu() {
    echo
    echo -e "${CYAN}╔════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║   Crucible AI Agents - Platform Management   ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════╝${NC}"
    echo
    echo -e "${MAGENTA}Main Commands:${NC}"
    echo "  1) Start platform"
    echo "  2) Stop platform"
    echo "  3) Restart platform"
    echo "  4) Check status"
    echo "  5) Check MCP tool list"
    echo "  6) View logs"
    echo "  7) View daemon monitor logs"
    echo "  8) Start local worker"
    echo "  9) Manage local watcher"
    echo
    echo -e "${MAGENTA}Advanced:${NC}"
    echo "  10) Force restart service"
    echo "  11) Rebuild and restart"
    echo "  12) Open shell menu"
    echo "  13) Sync MCP tools to registry"
    echo
    echo "  0) Exit"
    echo
}

# Service selection menu
show_service_menu() {
    echo >&2
    echo -e "${MAGENTA}Select service:${NC}" >&2
    echo "  1) all (all services)" >&2
    echo "  2) api" >&2
    echo "  3) db" >&2
    echo "  4) mcp_server" >&2
    echo "  5) watcher" >&2
    echo "  6) worker_container" >&2
    echo "  7) docker-proxy" >&2
    echo "  8) local_watcher" >&2
    echo "  9) local_worker" >&2
    echo "  0) Back" >&2
    echo >&2
}

# Shell operations menu
show_shell_menu() {
    echo
    echo -e "${MAGENTA}Shell Operations:${NC}"
    echo "  1) Start platform (background)"
    echo "  2) Stop platform (graceful)"
    echo "  3) Stop platform (force)"
    echo "  4) Get full status"
    echo "  5) Rebuild images"
    echo "  6) View container list"
    echo "  7) View network info"
    echo "  8) Clean up orphaned containers"
    echo "  0) Back"
    echo
}

# Get service selection
get_service() {
    show_service_menu
    read -r -p "Selection: " service_choice >&2
    case $service_choice in
        1) echo "all" ;;
        2) echo "api" ;;
        3) echo "db" ;;
        4) echo "mcp_server" ;;
        5) echo "watcher" ;;
        6) echo "worker_container" ;;
        7) echo "docker-proxy" ;;
        8) echo "local_watcher" ;;
        9) echo "local_worker" ;;
        0) echo "back" ;;
        *) echo "invalid" ;;
    esac
}

# Build frontend assets
build_frontend() {
    local frontend_dir="$PROJECT_ROOT/frontend"
    if [ ! -d "$frontend_dir" ]; then
        log_error "Frontend directory not found: $frontend_dir"
        return 1
    fi
    if ! command -v node &>/dev/null; then
        log_error "Node.js is not installed or not in PATH"
        return 1
    fi
    log_info "Installing frontend dependencies..."
    npm --prefix "$frontend_dir" ci
    log_info "Building frontend..."
    npm --prefix "$frontend_dir" run build
    log_success "Frontend built successfully → $frontend_dir/dist"
}

check_mcp_tool_list() {
    local api_base_url="${API_BASE_URL:-http://localhost:8080}"
    local normalized_base="${api_base_url%/}"
    local health_url="${normalized_base}/health"
    local tools_url="${normalized_base}/mcp/tools"
    local timeout_seconds="${MCP_TOOL_LIST_TIMEOUT_SECONDS:-15}"

    if ! command -v curl &>/dev/null; then
        log_error "curl is required to check MCP tool list"
        return 1
    fi

    log_info "Checking API health at $health_url"
    if ! curl -sf --max-time "$timeout_seconds" "$health_url" >/dev/null; then
        log_error "API health check failed at $health_url"
        return 1
    fi

    log_info "Fetching MCP tools via $tools_url"
    local response
    if ! response=$(curl -sS --max-time "$timeout_seconds" "$tools_url"); then
        log_error "Failed to fetch MCP tools from API"
        return 1
    fi

    if command -v jq &>/dev/null; then
        local tool_count
        tool_count=$(echo "$response" | jq -r '.tools | length' 2>/dev/null || echo "")
        if [[ "$tool_count" =~ ^[0-9]+$ ]]; then
            log_success "MCP connectivity confirmed via API (tool_count=$tool_count)"
            echo "$response" | jq -r '.tools[]?.name' | sed 's/^/  - /'
        else
            log_warn "Received unexpected MCP tools payload"
            echo "$response" | jq '.' 2>/dev/null || echo "$response"
        fi
    else
        log_success "MCP connectivity confirmed via API"
        echo "$response"
    fi
}

sync_mcp_registry_tools() {
    local api_base_url="${API_BASE_URL:-http://localhost:8080}"
    local normalized_base="${api_base_url%/}"
    local health_url="${normalized_base}/health"
    local sync_url="${normalized_base}/mcp/registry/tools/sync"
    local timeout_seconds="${MCP_TOOL_LIST_TIMEOUT_SECONDS:-15}"

    if ! command -v curl &>/dev/null; then
        log_error "curl is required to sync MCP registry tools"
        return 1
    fi

    log_info "Checking API health at $health_url"
    if ! curl -sf --max-time "$timeout_seconds" "$health_url" >/dev/null; then
        log_error "API health check failed at $health_url"
        return 1
    fi

    log_info "Syncing MCP tools into registry via $sync_url"
    local response
    if ! response=$(curl -sS --max-time "$timeout_seconds" -X POST "$sync_url"); then
        log_error "Failed to sync MCP tools into registry"
        return 1
    fi

    if command -v jq &>/dev/null; then
        local registered_count
        local skipped_count
        registered_count=$(echo "$response" | jq -r '.registered_count // ""' 2>/dev/null || echo "")
        skipped_count=$(echo "$response" | jq -r '.skipped_count // ""' 2>/dev/null || echo "")

        if [[ "$registered_count" =~ ^[0-9]+$ ]] && [[ "$skipped_count" =~ ^[0-9]+$ ]]; then
            log_success "MCP registry sync completed (registered=$registered_count, skipped=$skipped_count)"
            echo "$response" | jq -r '.registered_tools[]?' | sed 's/^/  + /'
            echo "$response" | jq -r '.skipped_tools[]?' | sed 's/^/  - /'
        else
            log_warn "Received unexpected MCP registry sync payload"
            echo "$response" | jq '.' 2>/dev/null || echo "$response"
        fi
    else
        log_success "MCP registry sync completed"
        echo "$response"
    fi
}

# Main loop
main() {
    cd "$PROJECT_ROOT"
    
    while true; do
        show_menu
        read -p "Select option: " choice
        
        case $choice in
            1)
                log_info "Starting platform..."
                bash "$SCRIPT_DIR/start.sh" --daemon
                ;;
            2)
                read -p "Remove containers? (y/n): " remove_choice
                if [[ "$remove_choice" =~ ^[Yy]$ ]]; then
                    bash "$SCRIPT_DIR/stop.sh" --remove
                else
                    bash "$SCRIPT_DIR/stop.sh"
                fi
                ;;
            3)
                bash "$SCRIPT_DIR/restart.sh"
                ;;
            4)
                bash "$SCRIPT_DIR/status.sh" --all
                ;;
            5)
                check_mcp_tool_list
                ;;
            6)
                service=$(get_service)
                if [ "$service" != "back" ] && [ "$service" != "invalid" ]; then
                    bash "$SCRIPT_DIR/logs.sh" "$service"
                fi
                ;;
            7)
                log_info "Daemon monitor logs (worker_container)..."
                docker-compose logs -f worker_container | grep daemon.monitor
                ;;
            8)
                if [ -f "$SCRIPT_DIR/run_local_worker.sh" ]; then
                    bash "$SCRIPT_DIR/run_local_worker.sh" start
                else
                    log_error "Local worker script not found"
                fi
                ;;
            9)
                # Local watcher management submenu
                while true; do
                    echo
                    echo -e "${MAGENTA}Local Watcher Options:${NC}"
                    echo "  1) Start local watcher"
                    echo "  2) Stop local watcher"
                    echo "  3) Restart local watcher"
                    echo "  4) Check local watcher status"
                    echo "  5) View local watcher logs"
                    echo "  0) Back"
                    echo
                    read -p "Selection: " watcher_choice
                    case $watcher_choice in
                        1)
                            bash "$SCRIPT_DIR/run_local_watcher.sh" start
                            ;;
                        2)
                            bash "$SCRIPT_DIR/run_local_watcher.sh" stop
                            ;;
                        3)
                            bash "$SCRIPT_DIR/run_local_watcher.sh" restart
                            ;;
                        4)
                            bash "$SCRIPT_DIR/run_local_watcher.sh" status
                            ;;
                        5)
                            bash "$SCRIPT_DIR/run_local_watcher.sh" logs -f
                            ;;
                        0)
                            break
                            ;;
                        *)
                            log_error "Invalid option"
                            ;;
                    esac
                    read -p "Press Enter to continue..."
                done
                ;;
            10)
                service=$(get_service)
                if [ "$service" != "back" ] && [ "$service" != "invalid" ]; then
                    bash "$SCRIPT_DIR/restart.sh" "$service" --hard
                fi
                ;;
            11)
                while true; do
                    echo
                    echo -e "${MAGENTA}Rebuild and Restart Options:${NC}"
                    echo "  1) Rebuild and restart a service"
                    echo "  2) Build frontend only (host)"
                    echo "  3) Build frontend then rebuild and restart a service"
                    echo "  4) Build frontend and restart frontend container"
                    echo "  0) Back"
                    echo
                    read -p "Selection: " rebuild_choice
                    case $rebuild_choice in
                        1)
                            service=$(get_service)
                            if [ "$service" != "back" ] && [ "$service" != "invalid" ]; then
                                bash "$SCRIPT_DIR/restart.sh" "$service" --rebuild
                            fi
                            ;;
                        2)
                            build_frontend
                            ;;
                        3)
                            build_frontend && \
                            service=$(get_service) && \
                            if [ "$service" != "back" ] && [ "$service" != "invalid" ]; then
                                bash "$SCRIPT_DIR/restart.sh" "$service" --rebuild
                            fi
                            ;;
                        4)
                            if build_frontend; then
                                log_info "Restarting frontend container..."
                                docker-compose restart frontend
                                log_success "Frontend container restarted with new build"
                            fi
                            ;;
                        0)
                            break
                            ;;
                        *)
                            log_error "Invalid option"
                            ;;
                    esac
                    read -p "Press Enter to continue..."
                done
                ;;
            12)
                while true; do
                    show_shell_menu
                    read -p "Selection: " shell_choice
                    case $shell_choice in
                        1)
                            docker-compose up -d
                            log_success "Platform started in background"
                            ;;
                        2)
                            docker-compose stop --timeout=30
                            log_success "Platform stopped gracefully"
                            ;;
                        3)
                            docker-compose kill
                            log_success "Platform force stopped"
                            ;;
                        4)
                            docker-compose ps
                            echo
                            ;;
                        5)
                            log_info "Building images..."
                            docker-compose build --no-cache
                            ;;
                        6)
                            docker-compose ps
                            ;;
                        7)
                            docker network ls | grep crucibleaiagents
                            ;;
                        8)
                            docker-compose down --remove-orphans
                            log_success "Orphaned containers removed"
                            ;;
                        0)
                            break
                            ;;
                        *)
                            log_error "Invalid option"
                            ;;
                    esac
                    read -p "Press Enter to continue..."
                done
                ;;
            13)
                sync_mcp_registry_tools
                ;;
            0)
                log_success "Goodbye!"
                exit 0
                ;;
            *)
                log_error "Invalid option"
                sleep 2
                ;;
        esac
    done
}

# Interactive menu only mode
if [[ $# -gt 0 ]]; then
    log_warn "Ignoring command-line arguments: manage.sh now runs in interactive menu mode only"
    echo
fi

main
