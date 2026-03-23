from fastapi import APIRouter, HTTPException
import logging
import json
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from schemas.model import Runs as Run, RunLogs, RunEvents, AgentPackage
from utils import config
from utils import dependency as dependencies

#from middleware.auth import _is_watcher_request
from services.run_service import (
    _to_utc_iso,
    _calculate_run_status,
    _get_run_logs,
    _get_run_events,
    _categorize_event,
    _extract_message,
)   
from services.package_service import (
    _get_missing_required_secret_keys_for_package,
    _refresh_package_secret_metadata,
)
from utils.logger import get_logger, log_event, log_exception

router = APIRouter()
LOGGER = get_logger("api.runs")


class RunEventIn(BaseModel):
    type: str
    payload: dict = Field(default_factory=dict)
    level: str | None = None
    category: str | None = None
    source: str | None = None
    message: str | None = None


class RunLogIn(BaseModel):
    stream: str = "stdout"
    level: str = "INFO"
    line: str
    section: str | None = None

@router.get("/runs")
async def list_runs():
    LOGGER.info("Listing all runs")
    with dependencies.db_session() as db:
        runs = db.query(Run).order_by(Run.id.desc()).all()
        return JSONResponse(content=[{
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
        } for run in runs])
    
@router.post("/runs")
def create_run(package_id: int):
    LOGGER.info(f"Creating new run for package ID: {package_id}")
    with dependencies.db_session() as db:
        # Validate package exists
        pkg = db.query(AgentPackage).filter(AgentPackage.id == package_id).first()
        if not pkg:
            raise HTTPException(status_code=404, detail="Package not found")

        missing_secret_keys = _get_missing_required_secret_keys_for_package(db, pkg)
        if missing_secret_keys:
            _refresh_package_secret_metadata(pkg, missing_secret_keys)
            db.commit()
            raise HTTPException(
                status_code=409,
                detail=(
                    "Package is on hold until required secrets are set. "
                    f"Missing secrets: {', '.join(missing_secret_keys)}"
                ),
            )

        # Create new run record using correct Runs model columns
        new_run = Run(
            agent_package_id=package_id,
            status="pending",
            timeout_seconds=pkg.timeout_seconds,
            runtime_mode=pkg.runtime_mode,
        )
        db.add(new_run)
        db.commit()
        db.refresh(new_run)

        log_event(LOGGER, logging.INFO, "run.created", f"Run {new_run.id} created for package {package_id}", run_id=new_run.id, package_id=package_id)

        return JSONResponse(content={
            "id": new_run.id,
            "agent_package_id": new_run.agent_package_id,
            "status": new_run.status,
            "runtime_mode": new_run.runtime_mode,
            "started_at": _to_utc_iso(new_run.started_at),
            "completed_at": _to_utc_iso(new_run.completed_at),
            "stopped_at": _to_utc_iso(new_run.stopped_at),
            "timeout_seconds": new_run.timeout_seconds,
            "exit_code": new_run.exit_code,
            "error": new_run.error,
            "container_id": new_run.container_id,
            "last_health_check": _to_utc_iso(new_run.last_health_check),
            "restart_count": new_run.restart_count,
            "exposed_port": new_run.exposed_port,
        })

@router.get("/runs/{run_id}")
def get_run(run_id: int):
    LOGGER.info(f"Retrieving run with ID: {run_id}")
    with dependencies.db_session() as db:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        return JSONResponse(content={
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
            "exposed_port": run.exposed_port,
            "restart_count": run.restart_count,
            "last_health_check": _to_utc_iso(run.last_health_check),
        })

@router.get("/runs/{run_id}/logs")
def get_run_logs(run_id: int):
    LOGGER.info(f"Retrieving logs for run ID: {run_id}")
    with dependencies.db_session() as db:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        logs = _get_run_logs(db, run_id)
        return JSONResponse(content=[{
            "id": log.id,
            "run_id": log.run_id,
            "ts": _to_utc_iso(log.ts),
            "stream": log.stream,
            "level": log.level,
            "line": log.line,
            "section": log.section,
        } for log in logs])

@router.get("/runs/{run_id}/events")
def get_run_events(run_id: int):
    LOGGER.info(f"Retrieving events for run ID: {run_id}")
    with dependencies.db_session() as db:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        events = _get_run_events(db, run_id)
        return JSONResponse(content=[{
            "id": event.id,
            "run_id": event.run_id,
            "ts": _to_utc_iso(event.ts),
            "type": event.type,
            "level": event.level,
            "category": event.category,
            "source": event.source,
            "message": event.message,
            "payload_jason": event.payload_jason,
        } for event in events])


@router.post("/runs/{run_id}/events")
def add_run_event(run_id: int, event: RunEventIn):
    LOGGER.info(f"Recording event for run ID: {run_id}")
    with dependencies.db_session() as db:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

        inferred_level, inferred_category, inferred_source = _categorize_event(event.type, event.payload)
        db_event = RunEvents(
            run_id=run_id,
            type=event.type,
            level=(event.level or inferred_level),
            category=(event.category or inferred_category),
            source=(event.source or inferred_source),
            message=(event.message or _extract_message(event.type, event.payload)),
            payload_jason=json.dumps(event.payload or {}),
        )
        db.add(db_event)

        # Mirror "log" type events to run_logs so they appear in the Logs tab.
        # Agents post log.info() / log.warning() calls as type="log" events via
        # the platform SDK (ApiLogHandler). Without this, the Logs tab is empty
        # for container/daemon runs that don't pipe stdout/stderr.
        if event.type == "log":
            payload_data = event.payload or {}
            log_line = payload_data.get("message") or event.message or ""
            log_level = (payload_data.get("level") or event.level or "INFO").upper()
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

        return JSONResponse(content={
            "id": db_event.id,
            "run_id": db_event.run_id,
            "ts": _to_utc_iso(db_event.ts),
            "type": db_event.type,
            "level": db_event.level,
            "category": db_event.category,
            "source": db_event.source,
            "message": db_event.message,
            "payload_jason": db_event.payload_jason,
        })


@router.post("/runs/{run_id}/logs")
def add_run_log(run_id: int, log: RunLogIn):
    LOGGER.info(f"Recording log line for run ID: {run_id}")
    with dependencies.db_session() as db:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

        db_log = RunLogs(
            run_id=run_id,
            stream=log.stream,
            level=log.level,
            line=log.line,
            section=log.section,
        )
        db.add(db_log)
        db.commit()
        db.refresh(db_log)

        return JSONResponse(content={
            "id": db_log.id,
            "run_id": db_log.run_id,
            "ts": _to_utc_iso(db_log.ts),
            "stream": db_log.stream,
            "level": db_log.level,
            "line": db_log.line,
            "section": db_log.section,
        })
    

@router.get("/runs/package/{package_id}")
def get_runs_by_package(package_id: int):
    LOGGER.info(f"Retrieving runs for package ID: {package_id}")
    with dependencies.db_session() as db:
        runs = db.query(Run).filter(Run.agent_package_id == package_id).order_by(Run.id.desc()).all()
        return JSONResponse(content=[{
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
        } for run in runs])



