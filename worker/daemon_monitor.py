"""
Daemon Monitor Service
Monitors health of daemon containers and handles restarts based on configured policies.
"""

import os
import time
import threading
from datetime import datetime, timezone

import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.utils.logger import get_logger, log_event, log_exception
from worker.daemon_manager import (
    get_active_daemon_runs,
    check_container_status,
    perform_health_check,
    should_restart,
    start_daemon_container,
    remove_daemon_container,
    update_daemon_run,
    get_daemon_run_info,
    capture_daemon_logs,
)

HEALTH_CHECK_INTERVAL = int(os.getenv("DAEMON_HEALTH_CHECK_INTERVAL", "30"))
LOGGER = get_logger("worker.daemon_monitor")


def _utc_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


def monitor_single_daemon(run: dict) -> None:
    """Monitor a single daemon run: check container status, health, and restart if needed."""
    run_id = run["id"]
    package_id = run["package_id"]
    container_id = run.get("container_id")
    
    log_event(
        LOGGER,
        20,
        "daemon.monitor.check_started",
        "Checking daemon run health",
        run_id=run_id,
        package_id=package_id,
        container_id=container_id[:12] if container_id else None,
    )
    
    # Validate container_id exists
    if not container_id:
        log_event(
            LOGGER,
            40,
            "daemon.monitor.missing_container_id",
            "No container ID for daemon run",
            run_id=run_id,
            package_id=package_id,
        )
        update_daemon_run(run_id, status="failed", error="No container ID tracked")
        return
    
    # Check if container exists and is running
    status = check_container_status(container_id)
    
    if status is None:
        log_event(
            LOGGER,
            40,
            "daemon.monitor.container_not_found",
            "Container not found - may have been removed",
            run_id=run_id,
            package_id=package_id,
            container_id=container_id[:12],
        )
        update_daemon_run(run_id, status="failed", error="Container not found")
        return
    
    # Container has exited
    if not status["running"]:
        exit_code = status.get("exit_code", -1)
        restart_policy = run["restart_policy"]
        restart_count = run["restart_count"]
        
        log_event(
            LOGGER,
            30,
            "daemon.monitor.container_exited",
            "Daemon container exited",
            run_id=run_id,
            package_id=package_id,
            container_id=container_id[:12],
            exit_code=exit_code,
            restart_policy=restart_policy,
            restart_count=restart_count,
        )
        
        # Check if we should restart
        if should_restart(restart_policy, exit_code, restart_count):
            log_event(
                LOGGER,
                30,
                "daemon.monitor.restarting",
                "Restarting daemon based on policy",
                run_id=run_id,
                package_id=package_id,
                exit_code=exit_code,
                attempt=restart_count + 1,
            )
            
            try:
                # Clean up old container
                remove_daemon_container(container_id)
                
                # Get fresh run info
                run_info = get_daemon_run_info(run_id)
                if not run_info:
                    log_event(
                        LOGGER,
                        40,
                        "daemon.monitor.restart_run_not_found",
                        "Run not found during restart attempt",
                        run_id=run_id,
                    )
                    update_daemon_run(run_id, status="failed", error="Run not found")
                    return
                
                # Start new container
                new_container_id, new_exposed_port = start_daemon_container(run_info)
                
                # Update database with new container info
                update_daemon_run(
                    run_id,
                    container_id=new_container_id,
                    exposed_port=new_exposed_port,
                    restart_count=restart_count + 1,
                    status="running",
                    last_health_check=_utc_now(),
                )
                
                log_event(
                    LOGGER,
                    20,
                    "daemon.monitor.restart_succeeded",
                    "Daemon restarted successfully",
                    run_id=run_id,
                    package_id=package_id,
                    new_container_id=new_container_id[:12],
                    exposed_port=new_exposed_port,
                    attempt=restart_count + 1,
                )
                
            except Exception as e:
                log_exception(
                    LOGGER,
                    "daemon.monitor.restart_failed",
                    "Failed to restart daemon",
                    run_id=run_id,
                    package_id=package_id,
                )
                update_daemon_run(
                    run_id,
                    status="failed",
                    error=f"Restart failed: {str(e)[:200]}"
                )
        else:
            # Reached max restarts or policy says never restart
            log_event(
                LOGGER,
                30,
                "daemon.monitor.not_restarting",
                "Daemon will not be restarted based on policy",
                run_id=run_id,
                package_id=package_id,
                exit_code=exit_code,
                restart_policy=restart_policy,
            )
            terminal_time = _utc_now()
            if exit_code == 0:
                # A clean daemon exit should be treated as a completed run.
                update_daemon_run(
                    run_id,
                    status="completed",
                    completed_at=terminal_time,
                    stopped_at=terminal_time,
                    exit_code=exit_code,
                )
            else:
                update_daemon_run(
                    run_id,
                    status="stopped",
                    stopped_at=terminal_time,
                    exit_code=exit_code,
                )
        return
    
    # Container is running - capture logs periodically
    if container_id:
        capture_daemon_logs(run_id, container_id)

    # Container is running - perform health check if configured
    health_config = run.get("health_check_config", {})
    if health_config and health_config.get("enabled"):
        exposed_port = run.get("exposed_port")
        if perform_health_check(exposed_port, health_config.get("path", "/health")):
            log_event(
                LOGGER,
                20,
                "daemon.monitor.health_check_passed",
                "Health check passed",
                run_id=run_id,
                package_id=package_id,
                exposed_port=exposed_port,
            )
            update_daemon_run(run_id, last_health_check=_utc_now())
        else:
            log_event(
                LOGGER,
                30,
                "daemon.monitor.health_check_failed",
                "Health check failed",
                run_id=run_id,
                package_id=package_id,
                exposed_port=exposed_port,
            )
            # Health check failure may trigger restart based on policy


def start_daemon_monitor_loop(poll_interval: int = None) -> threading.Thread:
    """Start daemon monitoring loop in background thread.
    
    Args:
        poll_interval: Seconds between health checks (default: DAEMON_HEALTH_CHECK_INTERVAL env var)
    
    Returns:
        Monitor thread (daemon thread, will exit when main thread exits)
    """
    poll_interval = poll_interval or HEALTH_CHECK_INTERVAL
    
    def monitor_loop():
        log_event(LOGGER, 20, "daemon.monitor.started", f"Daemon monitor loop started (interval={poll_interval}s)")
        
        while True:
            try:
                active_runs = get_active_daemon_runs()
                
                if active_runs:
                    log_event(
                        LOGGER,
                        20,
                        "daemon.monitor.poll",
                        f"Checking {len(active_runs)} active daemon(s)",
                    )
                    
                    for run in active_runs:
                        try:
                            monitor_single_daemon(run)
                        except Exception as e:
                            log_exception(
                                LOGGER,
                                "daemon.monitor.run_check_error",
                                "Error checking daemon run",
                                run_id=run.get("id"),
                                package_id=run.get("package_id"),
                                error=str(e),
                            )
                
                time.sleep(poll_interval)
                
            except Exception as e:
                log_exception(
                    LOGGER,
                    "daemon.monitor.loop_error",
                    "Error in daemon monitor loop",
                )
                time.sleep(poll_interval)
    
    thread = threading.Thread(target=monitor_loop, daemon=True)
    thread.start()
    
    log_event(LOGGER, 20, "daemon.monitor.thread_started", "Daemon monitor thread started")
    return thread
