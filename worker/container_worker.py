#!/usr/bin/env python3
"""Dedicated worker for container deployed agents (Docker runner execution).

Architecture:
- Main thread: Claims and executes batch/daemon runs from queue; inline scheduler polling
- Daemon monitor thread: Continuously monitors active daemon containers, health checks, restarts
"""

import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.utils.logger import get_logger, log_event, log_exception
from worker.scheduler import check_and_create_scheduled_runs
from worker.worker import (
    _claim_next_run_for,
    _enqueue_autostart_daemon_runs,
    _execute_run,
    reconcile_batch_container_runs,
    wait_for_database_ready,
)
from worker.daemon_monitor import start_daemon_monitor_loop

LOGGER = get_logger("worker.container")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "5"))
DAEMON_HEALTH_CHECK_INTERVAL = int(os.getenv("DAEMON_HEALTH_CHECK_INTERVAL", "30"))
MAX_CONCURRENT_RUNS = int(os.getenv("MAX_CONCURRENT_RUNS", "10"))
# How often (seconds) to check for due scheduled runs
SCHEDULER_CHECK_INTERVAL = int(os.getenv("SCHEDULER_CHECK_INTERVAL", "15"))
# How often (seconds) to enqueue daemon packages marked for auto-start.
DAEMON_AUTOSTART_CHECK_INTERVAL = int(os.getenv("DAEMON_AUTOSTART_CHECK_INTERVAL", "30"))
# How often (seconds) to reconcile stale/exited batch containers
BATCH_CONTAINER_RECONCILE_INTERVAL = int(os.getenv("BATCH_CONTAINER_RECONCILE_INTERVAL", "30"))


def main() -> None:
    if not wait_for_database_ready():
        return

    # Auto-enqueue daemon packages marked for auto-start
    _enqueue_autostart_daemon_runs("container")
    reconcile_batch_container_runs()

    # Start daemon monitor thread for health checks and restarts
    start_daemon_monitor_loop(DAEMON_HEALTH_CHECK_INTERVAL)

    log_event(
        LOGGER,
        logging.INFO,
        "worker.container.startup",
        "Container worker started",
        poll_seconds=POLL_SECONDS,
        health_check_interval=DAEMON_HEALTH_CHECK_INTERVAL,
        max_concurrent_runs=MAX_CONCURRENT_RUNS,
        scheduler_check_interval=SCHEDULER_CHECK_INTERVAL,
        batch_container_reconcile_interval=BATCH_CONTAINER_RECONCILE_INTERVAL,
    )

    executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_RUNS, thread_name_prefix="agent-run")
    last_scheduler_check = 0.0  # Force an immediate check on first iteration
    last_autostart_check = 0.0  # Force an immediate check on first iteration
    last_reconcile_check = 0.0  # Force an immediate check on first iteration
    try:
        while True:
            # Inline scheduler: fire due scheduled runs
            now = time.monotonic()
            if now - last_scheduler_check >= SCHEDULER_CHECK_INTERVAL:
                try:
                    enqueued = check_and_create_scheduled_runs(deployment="container")
                    if enqueued:
                        log_event(LOGGER, logging.INFO, "worker.container.scheduler_tick",
                                  "Scheduled runs enqueued", count=enqueued)
                except Exception as sched_exc:
                    log_exception(LOGGER, "worker.container.scheduler_error",
                                  "Error in scheduler tick", error=str(sched_exc))
                last_scheduler_check = now

            # Periodically enqueue daemon packages created after worker startup.
            if now - last_autostart_check >= DAEMON_AUTOSTART_CHECK_INTERVAL:
                try:
                    _enqueue_autostart_daemon_runs("container")
                except Exception as auto_exc:
                    log_exception(
                        LOGGER,
                        "worker.container.daemon_autostart_error",
                        "Error while enqueueing daemon auto-start runs",
                        error=str(auto_exc),
                    )
                last_autostart_check = now

            if now - last_reconcile_check >= BATCH_CONTAINER_RECONCILE_INTERVAL:
                try:
                    reconciled = reconcile_batch_container_runs()
                    if reconciled:
                        log_event(
                            LOGGER,
                            logging.INFO,
                            "worker.container.batch_reconcile_tick",
                            "Batch container reconciliation completed",
                            count=reconciled,
                        )
                except Exception as reconcile_exc:
                    log_exception(
                        LOGGER,
                        "worker.container.batch_reconcile_error",
                        "Error while reconciling batch containers",
                        error=str(reconcile_exc),
                    )
                last_reconcile_check = now

            try:
                run = _claim_next_run_for("container")
            except Exception as exc:
                log_exception(LOGGER, "worker.container.claim_error", "Error claiming next run", error=str(exc))
                time.sleep(POLL_SECONDS)
                continue

            if not run:
                time.sleep(POLL_SECONDS)
                continue

            executor.submit(_execute_run, run)
            # Small sleep to avoid tight-loop when many runs are queued
            time.sleep(0.1)
    except KeyboardInterrupt:
        log_event(LOGGER, logging.INFO, "worker.container.shutdown", "Container worker stopped")
    finally:
        executor.shutdown(wait=True, cancel_futures=False)


if __name__ == "__main__":
    main()
