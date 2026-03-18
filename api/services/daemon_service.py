import logging
import subprocess
from datetime import datetime, timezone
from schemas.model import AgentPackage, Runs as Run
from utils.dependency import db_session
from utils.logger import get_logger, log_event, log_exception

_LOGGER = get_logger("api.startup.daemon")


def _cleanup_stale_daemon_runs():
    """Clean up daemon runs from previous sessions and mark them as stopped."""
    try:
        with db_session() as db:
            # Find all daemon runs that are in "running" state (from previous sessions)
            stale_daemon_runs = db.query(Run).filter(
                Run.runtime_mode == "daemon",
                Run.status == "running"
            ).all()

            if stale_daemon_runs:
                log_event(_LOGGER, logging.INFO, "startup.daemon_cleanup_start",
                          "Cleaning up stale daemon runs from previous session",
                          count=len(stale_daemon_runs))

                for run in stale_daemon_runs:
                    run_id = run.id

                    # Try to stop the associated Docker container if it exists
                    try:
                        container_name = f"agentflow_daemon_{run_id}"
                        subprocess.run(
                            ["docker", "stop", container_name],
                            timeout=5,
                            capture_output=True
                        )
                        subprocess.run(
                            ["docker", "rm", "-f", container_name],
                            timeout=5,
                            capture_output=True
                        )
                        log_event(_LOGGER, logging.INFO, "startup.daemon_container_removed",
                                  "Stopped and removed stale daemon container",
                                  run_id=run_id, container_name=container_name)
                    except Exception as e:
                        log_event(_LOGGER, logging.WARNING, "startup.daemon_container_stop_failed",
                                  "Could not stop stale daemon container",
                                  run_id=run_id, error=str(e))

                    # Mark the run as stopped
                    run.status = "stopped"
                    run.stopped_at = datetime.now(timezone.utc)
                    db.add(run)
                    log_event(_LOGGER, logging.INFO, "startup.daemon_run_marked_stopped",
                              "Marked stale daemon run as stopped",
                              run_id=run_id)

                db.commit()
            else:
                log_event(_LOGGER, logging.INFO, "startup.daemon_cleanup_none",
                          "No stale daemon runs to clean up")

            # Find all BATCH runs that are in "running" state with no associated container
            stale_batch_runs = db.query(Run).filter(
                Run.runtime_mode == "batch",
                Run.status == "running"
            ).all()

            if stale_batch_runs:
                log_event(_LOGGER, logging.INFO, "startup.batch_stale_check",
                          "Checking stale batch runs from previous session",
                          count=len(stale_batch_runs))

                for run in stale_batch_runs:
                    run_id = run.id
                    container_name = f"agentflow_run_{run_id}"

                    # Check if container still exists
                    try:
                        result = subprocess.run(
                            ["docker", "inspect", container_name],
                            timeout=5,
                            capture_output=True
                        )

                        if result.returncode == 0:
                            # Container exists but worker didn't update status — leave it alone
                            log_event(_LOGGER, logging.INFO, "startup.batch_run_container_exists",
                                      "Batch run container still exists; skipping",
                                      run_id=run_id, container_name=container_name)
                            continue
                        else:
                            # Container gone — mark run as failed
                            log_event(_LOGGER, logging.WARNING, "startup.batch_run_container_missing",
                                      "Batch run container not found; marking run as failed",
                                      run_id=run_id, container_name=container_name)
                            run.status = "failed"
                            run.error = "Container was removed before run completed"
                            run.stopped_at = datetime.now(timezone.utc)
                            db.add(run)

                    except Exception as e:
                        log_event(_LOGGER, logging.WARNING, "startup.batch_run_check_failed",
                                  "Error checking stale batch run container",
                                  run_id=run_id, error=str(e))

                db.commit()
            else:
                log_event(_LOGGER, logging.INFO, "startup.batch_stale_none",
                          "No stale batch runs found")

    except Exception as e:
        log_exception(_LOGGER, "startup.daemon_cleanup_error",
                      "Error during stale run cleanup", error=str(e))


def _load_auto_start_daemons():
    """Auto-start daemon agents on API startup."""
    try:
        with db_session() as db:
            # Find all packages marked for auto-start
            auto_start_packages = db.query(AgentPackage).filter(
                AgentPackage.runtime_mode == "daemon",
                AgentPackage.daemon_auto_start == True,
                AgentPackage.disabled == False
            ).all()

            started_count = 0
            for pkg in auto_start_packages:
                try:
                    # Check if already running (not failed or stopped)
                    existing_run = db.query(Run).filter(
                        Run.package_id == pkg.id,
                        Run.runtime_mode == "daemon",
                        Run.status.in_(["queued", "running"])
                    ).first()

                    if existing_run:
                        log_event(_LOGGER, logging.INFO, "startup.daemon_already_running",
                                  "Daemon already queued or running; skipping auto-start",
                                  package_id=pkg.id,
                                  package_name=pkg.name or pkg.filename,
                                  run_id=existing_run.id)
                        continue

                    # Create new daemon run
                    run = Run(
                        status="queued",
                        package_id=pkg.id,
                        timeout_seconds=pkg.timeout_seconds,
                        runtime_mode="daemon"
                    )
                    db.add(run)
                    db.commit()
                    db.refresh(run)

                    started_count += 1
                    log_event(_LOGGER, logging.INFO, "startup.daemon_auto_started",
                              "Daemon queued for auto-start",
                              package_id=pkg.id,
                              package_name=pkg.name or pkg.filename,
                              run_id=run.id)

                except Exception as e:
                    log_event(_LOGGER, logging.WARNING, "startup.daemon_auto_start_failed",
                              "Error queuing auto-start daemon",
                              package_id=pkg.id, error=str(e))

            log_event(_LOGGER, logging.INFO, "startup.daemon_auto_start_complete",
                      "Daemon auto-start complete",
                      started_count=started_count)

    except Exception as e:
        log_exception(_LOGGER, "startup.daemon_auto_start_error",
                      "Error loading auto-start daemons", error=str(e))
