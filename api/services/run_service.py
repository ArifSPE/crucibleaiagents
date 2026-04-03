from datetime import datetime, timezone
import json
from typing import Any, List, Optional, Tuple
from fastapi import HTTPException
from utils.logger import get_logger, log_event

LOGGER = get_logger("api.services.run_service")


def _to_utc_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _calculate_run_status(run: Any) -> str:
    status = (run.status or "").strip().lower()
    if status:
        return status
    if run.exit_code is not None:
        return "completed" if run.exit_code == 0 else "failed"
    if run.started_at and not run.completed_at and not run.stopped_at:
        return "running"
    if run.completed_at or run.stopped_at:
        return "completed"
    return "pending"


def _get_run_logs(db: Any, run_id: int) -> List[Any]:
    from schemas.model import RunLogs
    return db.query(RunLogs).filter(RunLogs.run_id == run_id).order_by(RunLogs.id.asc()).all()


def _get_run_events(db: Any, run_id: int) -> List[Any]:
    from schemas.model import RunEvents
    return db.query(RunEvents).filter(RunEvents.run_id == run_id).order_by(RunEvents.id.asc()).all()


def _categorize_event(event_type: str, payload: dict) -> Tuple[str, str, str]:
    """Extract level, category, and source from event type and payload.

    Returns: (level, category, source)
    """
    # Defaults
    level = "INFO"
    category = "system"
    source = "runner"

    # Categorize by event type
    if event_type == "runner_boot":
        level = "INFO"
        category = "infrastructure"
        source = "runner"

    elif event_type == "subprocess_start":
        level = "DEBUG"
        category = "infrastructure"
        source = "runner"

    elif event_type == "subprocess_end":
        level = "INFO"
        category = "infrastructure"
        source = "runner"

    elif event_type == "subprocess_error":
        level = "ERROR"
        category = "infrastructure"
        source = "runner"

    elif event_type == "exception":
        level = "ERROR"
        category = "agent"
        source = "agent"

    elif event_type == "step_start":
        level = "DEBUG"
        category = "telemetry"
        source = "agent"

    elif event_type == "step_end":
        level = "INFO"
        category = "telemetry"
        source = "agent"

    elif event_type == "step_error":
        level = "ERROR"
        category = "telemetry"
        source = "agent"

    elif event_type == "log":
        level = payload.get("level", "INFO")
        category = "agent"
        source = "agent"

    return level, category, source


def _extract_message(event_type: str, payload: dict) -> str:
    """Extract human-readable message from event."""
    if event_type == "runner_boot":
        python_ver = payload.get("python", "unknown").split()[0]
        return f"Runner started with Python {python_ver}"

    elif event_type == "subprocess_start":
        cmd = payload.get("cmd", "unknown")
        return f"Start: {cmd[:80]}"

    elif event_type == "subprocess_end":
        cmd = payload.get("cmd", "unknown")
        rc = payload.get("returncode", "?")
        ms = payload.get("ms", "?")
        return f"End: {cmd[:50]} (exit={rc}, {ms}ms)"

    elif event_type == "subprocess_error":
        error = payload.get("error", "unknown")
        return f"Error: {error[:100]}"

    elif event_type == "exception":
        exc_type = payload.get("exc_type", "Exception")
        message = payload.get("message", "")
        return f"{exc_type}: {message[:80]}"

    elif event_type == "step_start":
        name = payload.get("name", "unnamed")
        return f"Step started: {name}"

    elif event_type == "step_end":
        name = payload.get("name", "unnamed")
        ms = payload.get("ms", "?")
        return f"Step completed: {name} ({ms}ms)"

    elif event_type == "step_error":
        name = payload.get("name", "unnamed")
        error = payload.get("error", "unknown")
        return f"Step failed: {name} - {error[:60]}"

    elif event_type == "log":
        return payload.get("message", "")

    else:
        return str(payload)[:150]


def serialize_run(run: Any) -> dict:
    return {
        "id": run.id,
        "agent_package_id": run.agent_package_id,
        "status": _calculate_run_status(run),
        "runtime_mode": run.runtime_mode,
        "started_at": _to_utc_iso(run.started_at),
        "completed_at": _to_utc_iso(run.completed_at),
        "stopped_at": _to_utc_iso(run.stopped_at),
        "timeout_seconds": run.timeout_seconds,
        "exit_code": run.exit_code,
        "error": run.error,
        "container_id": run.container_id,
        "last_health_check": _to_utc_iso(run.last_health_check),
        "restart_count": run.restart_count,
        "exposed_port": run.exposed_port,
    }


def serialize_run_log(log: Any) -> dict:
    return {
        "id": log.id,
        "run_id": log.run_id,
        "ts": _to_utc_iso(log.ts),
        "stream": log.stream,
        "level": log.level,
        "line": log.line,
        "section": log.section,
    }


def serialize_run_event(event: Any) -> dict:
    return {
        "id": event.id,
        "run_id": event.run_id,
        "ts": _to_utc_iso(event.ts),
        "type": event.type,
        "level": event.level,
        "category": event.category,
        "source": event.source,
        "message": event.message,
        "payload_jason": event.payload_jason,
    }


def list_runs(db: Any) -> List[Any]:
    from schemas.model import Runs as Run
    runs = db.query(Run).order_by(Run.id.desc()).all()
    log_event(LOGGER, 20, "run.listed", "Listed runs", run_count=len(runs))
    return runs


def get_run_or_404(db: Any, run_id: int) -> Any:
    from schemas.model import Runs as Run
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        log_event(LOGGER, 30, "run.not_found", "Run not found", run_id=run_id)
        raise HTTPException(status_code=404, detail="Run not found")
    log_event(LOGGER, 10, "run.retrieved", "Retrieved run", run_id=run_id)
    return run


def create_run(db: Any, package_id: int) -> Any:
    from schemas.model import Runs as Run, AgentPackage
    from services.package_service import _get_missing_required_secret_keys_for_package, _refresh_package_secret_metadata

    pkg = db.query(AgentPackage).filter(AgentPackage.id == package_id).first()
    if not pkg:
        log_event(LOGGER, 30, "run.create.package_not_found", "Run creation failed: package not found", package_id=package_id)
        raise HTTPException(status_code=404, detail="Package not found")

    missing_secret_keys = _get_missing_required_secret_keys_for_package(db, pkg)
    if missing_secret_keys:
        _refresh_package_secret_metadata(pkg, missing_secret_keys)
        db.commit()
        log_event(
            LOGGER,
            30,
            "run.create.blocked_missing_secrets",
            "Run creation blocked: required secrets missing",
            package_id=package_id,
            missing_secret_keys_count=len(missing_secret_keys),
        )
        raise HTTPException(
            status_code=409,
            detail=(
                "Package is on hold until required secrets are set. "
                f"Missing secrets: {', '.join(missing_secret_keys)}"
            ),
        )

    new_run = Run(
        agent_package_id=package_id,
        status="pending",
        timeout_seconds=pkg.timeout_seconds,
        runtime_mode=pkg.runtime_mode,
    )
    db.add(new_run)
    db.commit()
    db.refresh(new_run)
    log_event(
        LOGGER,
        20,
        "run.created",
        "Created run",
        run_id=new_run.id,
        package_id=package_id,
        runtime_mode=new_run.runtime_mode,
    )
    return new_run


def list_runs_by_package(db: Any, package_id: int) -> List[Any]:
    from schemas.model import Runs as Run
    runs = db.query(Run).filter(Run.agent_package_id == package_id).order_by(Run.id.desc()).all()
    log_event(LOGGER, 20, "run.listed_by_package", "Listed runs by package", package_id=package_id, run_count=len(runs))
    return runs


def add_run_event(db: Any, run_id: int, event_type: str, payload: dict, level: Optional[str], category: Optional[str], source: Optional[str], message: Optional[str]) -> Any:
    from schemas.model import RunEvents, RunLogs

    get_run_or_404(db, run_id)
    inferred_level, inferred_category, inferred_source = _categorize_event(event_type, payload)
    db_event = RunEvents(
        run_id=run_id,
        type=event_type,
        level=(level or inferred_level),
        category=(category or inferred_category),
        source=(source or inferred_source),
        message=(message or _extract_message(event_type, payload)),
        payload_jason=json.dumps(payload or {}),
    )
    db.add(db_event)

    if event_type == "log":
        payload_data = payload or {}
        log_line = payload_data.get("message") or message or ""
        log_level = (payload_data.get("level") or level or "INFO").upper()
        if log_line:
            db_log = RunLogs(
                run_id=run_id,
                stream="sdk",
                level=log_level,
                line=log_line,
                section="agent",
            )
            db.add(db_log)

    db.commit()
    db.refresh(db_event)
    log_event(
        LOGGER,
        10,
        "run.event.added",
        "Added run event",
        run_id=run_id,
        run_event_type=event_type,
        event_level=db_event.level,
        category=db_event.category,
        source=db_event.source,
    )
    return db_event


def add_run_log(db: Any, run_id: int, stream: str, level: str, line: str, section: Optional[str]) -> Any:
    from schemas.model import RunLogs

    get_run_or_404(db, run_id)
    db_log = RunLogs(
        run_id=run_id,
        stream=stream,
        level=level,
        line=line,
        section=section,
    )
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    log_event(
        LOGGER,
        10,
        "run.log.added",
        "Added run log",
        run_id=run_id,
        stream=stream,
        log_level=level,
        section=section,
    )
    return db_log
