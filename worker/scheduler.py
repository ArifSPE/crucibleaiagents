#!/usr/bin/env python3
"""Schedule checker for the worker process.

Responsible for polling ``package_schedules`` and enqueuing runs that are due.
Intentionally kept separate from the API layer — the API handles OLTP schedule
CRUD, and this module handles the backend scheduling work (fire-and-forget
run creation) inside the worker process.

Uses raw SQL (SQLAlchemy text) consistent with the rest of the worker codebase
so there is no dependency on API models or services.
"""

from __future__ import annotations

import json
import logging
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generator, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.utils.db import SessionLocal  # noqa: E402
from api.utils.logger import get_logger, log_event, log_exception  # noqa: E402

LOGGER = get_logger("worker.scheduler")


@contextmanager
def _db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def calculate_next_run_time(
    schedule_type: str,
    schedule_config: dict,
    last_run_time: Optional[datetime] = None,
) -> Optional[datetime]:
    """Return the next UTC datetime for a schedule, or None if not calculable."""
    now = _utc_now()

    if schedule_type == "interval":
        interval_seconds = int(schedule_config.get("interval_seconds", 3600))
        base = _as_utc(last_run_time) if last_run_time else now
        return base + timedelta(seconds=interval_seconds)

    if schedule_type == "cron":
        cron_expr = schedule_config.get("cron_expr", "0 0 * * *")
        try:
            from croniter import croniter  # optional dependency
            return _as_utc(croniter(cron_expr, now).get_next(datetime))
        except ImportError:
            return now + timedelta(hours=1)
        except Exception:
            return None

    if schedule_type == "at":
        raw = schedule_config.get("timestamp")
        if raw:
            try:
                scheduled = _as_utc(datetime.fromisoformat(raw.replace("Z", "+00:00")))
                return scheduled if scheduled > now else None
            except Exception:
                return None

    return None


def check_and_create_scheduled_runs(deployment: Optional[str] = None) -> int:
    """Enqueue runs for all package schedules that are currently due.

    For each active schedule whose ``next_run_time`` is in the past:
    - Skips packages that are disabled.
    - Skips if a run is already pending / queued / running for the package.
    - Inserts a ``queued`` run and advances ``last_run_time`` / ``next_run_time``.

    Args:
        deployment: If set (``'container'`` or ``'local'``), only schedules for
            packages with that deployment type are processed.  This prevents a
            container worker from enqueuing runs that only a local worker can
            claim, and vice-versa.

    Returns the number of runs enqueued.
    """
    now = _utc_now()
    created = 0

    deployment_value = (deployment or "").strip().lower() or None
    if deployment_value == "container":
        deployment_filter = "AND LOWER(COALESCE(ap.deployment, '')) = 'container'"
    elif deployment_value == "local":
        deployment_filter = "AND COALESCE(NULLIF(TRIM(LOWER(ap.deployment)), ''), 'local') = 'local'"
    else:
        deployment_filter = ""

    try:
        with _db() as db:
            due_rows = db.execute(text(f"""
                SELECT ps.id        AS schedule_id,
                       ps.package_id,
                       ps.schedule_type,
                       ps.schedule_config,
                       ps.last_run_time,
                       ap.timeout_seconds,
                       ap.runtime_mode
                FROM   package_schedules ps
                JOIN   agent_packages    ap ON ap.id = ps.package_id
                WHERE  ps.is_active = true
                  AND  ps.next_run_time <= :now
                  AND  COALESCE(ap.disabled, false) = false
                  {deployment_filter}
            """), {"now": now}).fetchall()

            for row in due_rows:
                try:
                    # Skip if an active run already exists for this package
                    active = db.execute(text("""
                        SELECT id FROM runs
                        WHERE  agent_package_id = :pkg_id
                          AND  status IN ('pending', 'queued', 'running')
                        LIMIT 1
                    """), {"pkg_id": row.package_id}).fetchone()
                    if active:
                        continue

                    # Insert a queued run
                    result = db.execute(text("""
                        INSERT INTO runs (agent_package_id, status, runtime_mode,
                                          timeout_seconds, restart_count)
                        VALUES (:pkg_id, 'queued', :runtime_mode,
                                :timeout_seconds, 0)
                        RETURNING id
                    """), {
                        "pkg_id": row.package_id,
                        "runtime_mode": row.runtime_mode or "batch",
                        "timeout_seconds": row.timeout_seconds or 60,
                    })
                    run_id = result.fetchone()[0]

                    # Advance schedule metadata
                    config = json.loads(row.schedule_config or "{}")
                    next_run = calculate_next_run_time(
                        row.schedule_type, config, last_run_time=now
                    )
                    db.execute(text("""
                        UPDATE package_schedules
                        SET    last_run_time = :last_run,
                               next_run_time = :next_run
                        WHERE  id = :schedule_id
                    """), {
                        "last_run": now,
                        "next_run": next_run,
                        "schedule_id": row.schedule_id,
                    })

                    created += 1
                    log_event(
                        LOGGER,
                        logging.INFO,
                        "scheduler.run_enqueued",
                        "Scheduled run enqueued",
                        package_id=row.package_id,
                        schedule_id=row.schedule_id,
                        run_id=run_id,
                        next_run_time=next_run.isoformat() if next_run else None,
                    )

                except Exception as inner_exc:
                    log_exception(
                        LOGGER,
                        "scheduler.enqueue_error",
                        "Error enqueuing scheduled run",
                        schedule_id=row.schedule_id,
                        package_id=row.package_id,
                        error=str(inner_exc),
                    )

    except Exception as exc:
        log_exception(LOGGER, "scheduler.check_error", "Error checking scheduled runs", error=str(exc))

    return created
