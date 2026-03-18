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
    echo "  5) View logs"
    echo "  6) View daemon monitor logs"
    echo "  7) Start local worker"
    echo "  8) Manage local watcher"
    echo
    echo -e "${MAGENTA}Advanced:${NC}"
    echo "  9) Force restart service"
    echo "  10) Rebuild and restart"
    echo "  11) Open shell menu"
    echo
    echo "  0) Exit"
    echo
}

# Service selection menu
show_service_menu() {
    echo
    echo -e "${MAGENTA}Select service:${NC}"
    echo "  1) all (all services)"
    echo "  2) api"
    echo "  3) db"
    echo "  4) watcher"
    echo "  5) worker_container"
    echo "  6) docker-proxy"
    echo "  7) local_watcher"
    echo "  0) Back"
    echo
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
    read -p "Selection: " service_choice
    case $service_choice in
        1) echo "all" ;;
        2) echo "api" ;;
        3) echo "db" ;;
        4) echo "watcher" ;;
        5) echo "worker_container" ;;
        6) echo "docker-proxy" ;;
        7) echo "local_watcher" ;;
        0) echo "back" ;;
        *) echo "invalid" ;;
    esac
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
                service=$(get_service)
                if [ "$service" != "back" ] && [ "$service" != "invalid" ]; then
                    bash "$SCRIPT_DIR/logs.sh" "$service"
                fi
                ;;
            6)
                log_info "Daemon monitor logs (worker_container)..."
                docker-compose logs -f worker_container | grep daemon.monitor
                ;;
            7)
                if [ -x "$SCRIPT_DIR/run_local_worker_host.sh" ]; then
                    bash "$SCRIPT_DIR/run_local_worker_host.sh"
                else
                    log_error "Local worker script not found"
                fi
                ;;
            8)
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
            9)
                service=$(get_service)
                if [ "$service" != "back" ] && [ "$service" != "invalid" ]; then
                    bash "$SCRIPT_DIR/restart.sh" "$service" --hard
                fi
                ;;
            10)
                service=$(get_service)
                if [ "$service" != "back" ] && [ "$service" != "invalid" ]; then
                    bash "$SCRIPT_DIR/restart.sh" "$service" --rebuild
                fi
                ;;
            11)
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

# If argument provided, run as CLI mode
if [[ $# -gt 0 ]]; then
    case $1 in
        start)
            shift
            bash "$SCRIPT_DIR/start.sh" "$@"
            ;;
        stop)
            shift
            bash "$SCRIPT_DIR/stop.sh" "$@"
            ;;
        restart)
            shift
            bash "$SCRIPT_DIR/restart.sh" "$@"
            ;;
        status)
            shift
            bash "$SCRIPT_DIR/status.sh" "$@"
            ;;
        logs)
            shift
            bash "$SCRIPT_DIR/logs.sh" "$@"
            ;;
        watcher)
            shift
            bash "$SCRIPT_DIR/run_local_watcher.sh" "$@"
            ;;
        *)
            cat << EOF
Usage: $0 [COMMAND] [OPTIONS]

COMMANDS:
    start [OPTIONS]        Start platform
    stop [OPTIONS]         Stop platform
    restart [OPTIONS]      Restart services
    status [OPTIONS]       Check platform status
    logs [SERVICE]         View service logs
    watcher [CMD] [OPTS]   Manage local watcher (start|stop|restart|status|logs)
    (no args)              Interactive menu

EXAMPLES:
    $0 start --daemon
    $0 status --all
    $0 logs api
    $0 logs local_watcher -f
    $0 watcher start
    $0 watcher logs -f
    $0 restart worker_container

Run '$0 COMMAND --help' for command-specific options.

EOF
            exit 1
            ;;
    esac
else
    # Interactive mode
    main
fi
