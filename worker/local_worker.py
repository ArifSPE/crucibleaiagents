#!/usr/bin/env python3
"""Dedicated worker for locally deployed agents (subprocess execution)."""

import logging
import os
import sys
import time
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
    wait_for_database_ready,
)

LOGGER = get_logger("worker.local")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "5"))
SCHEDULER_CHECK_INTERVAL = int(os.getenv("SCHEDULER_CHECK_INTERVAL", "15"))
# How often (seconds) to enqueue daemon packages marked for auto-start.
DAEMON_AUTOSTART_CHECK_INTERVAL = int(os.getenv("DAEMON_AUTOSTART_CHECK_INTERVAL", "30"))


def main() -> None:
    if not wait_for_database_ready():
        return

    runner_token = (
        os.getenv("AGENTFLOW_RUNNER_API_TOKEN")
        or os.getenv("AGENTFLOW_API_TOKEN")
        or os.getenv("API_TOKEN", "")
    )
    if not runner_token:
        log_event(
            LOGGER, logging.WARNING,
            "worker.startup.no_api_token",
            "AGENTFLOW_RUNNER_API_TOKEN is not set — runner API calls will be unauthenticated",
        )

    _enqueue_autostart_daemon_runs("local")
    log_event(LOGGER, logging.INFO, "worker.local.startup", "Local worker started", poll_seconds=POLL_SECONDS)
    last_scheduler_check = 0.0  # Force an immediate check on the first iteration
    last_autostart_check = 0.0  # Force an immediate check on the first iteration
    while True:
        try:
            now = time.monotonic()
            if now - last_scheduler_check >= SCHEDULER_CHECK_INTERVAL:
                try:
                    enqueued = check_and_create_scheduled_runs(deployment="local")
                    if enqueued:
                        log_event(
                            LOGGER, logging.INFO,
                            "worker.local.scheduler",
                            "Scheduler enqueued scheduled runs",
                            count=enqueued,
                        )
                except Exception as exc:
                    log_exception(LOGGER, "worker.local.scheduler_error", "Scheduler check failed", error=str(exc))
                last_scheduler_check = time.monotonic()

            # Periodically enqueue daemon packages created after worker startup.
            if now - last_autostart_check >= DAEMON_AUTOSTART_CHECK_INTERVAL:
                try:
                    _enqueue_autostart_daemon_runs("local")
                except Exception as exc:
                    log_exception(
                        LOGGER,
                        "worker.local.daemon_autostart_error",
                        "Daemon auto-start enqueue failed",
                        error=str(exc),
                    )
                last_autostart_check = time.monotonic()

            run = _claim_next_run_for("local")
            if not run:
                time.sleep(POLL_SECONDS)
                continue
            _execute_run(run)
        except KeyboardInterrupt:
            log_event(LOGGER, logging.INFO, "worker.local.shutdown", "Local worker stopped")
            break
        except Exception as exc:
            log_exception(LOGGER, "worker.local.loop_error", "Unhandled local worker loop error", error=str(exc))
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
