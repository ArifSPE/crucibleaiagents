from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple


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
