from fastapi import APIRouter, Request
import logging
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from utils import dependency as dependencies
from utils.rate_limit import limiter

#from middleware.auth import _is_watcher_request
from services.run_service import (
    serialize_run,
    serialize_run_log,
    serialize_run_event,
    list_runs as svc_list_runs,
    get_run_or_404,
    create_run as svc_create_run,
    list_runs_by_package as svc_list_runs_by_package,
    add_run_event as svc_add_run_event,
    add_run_log as svc_add_run_log,
    _get_run_logs,
    _get_run_events,
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


class RunCreateRequest(BaseModel):
    package_id: int


class RunLogIn(BaseModel):
    stream: str = "stdout"
    level: str = "INFO"
    line: str = Field(..., max_length=10_000)
    section: str | None = None

@router.get("/runs")
async def list_runs():
    LOGGER.info("Listing all runs")
    with dependencies.db_session() as db:
        runs = svc_list_runs(db)
        return JSONResponse(content=[serialize_run(run) for run in runs])
    
@router.post("/runs")
@limiter.limit("60/minute")
def create_run(request: Request, body: RunCreateRequest):
    package_id = body.package_id
    LOGGER.info(f"Creating new run for package ID: {package_id}")
    with dependencies.db_session() as db:
        new_run = svc_create_run(db, package_id)

        log_event(LOGGER, logging.INFO, "run.created", f"Run {new_run.id} created for package {package_id}", run_id=new_run.id, package_id=package_id)
        return JSONResponse(content=serialize_run(new_run))

@router.get("/runs/{run_id}")
def get_run(run_id: int):
    LOGGER.info(f"Retrieving run with ID: {run_id}")
    with dependencies.db_session() as db:
        run = get_run_or_404(db, run_id)
        return JSONResponse(content=serialize_run(run))

@router.get("/runs/{run_id}/logs")
def get_run_logs(run_id: int):
    LOGGER.info(f"Retrieving logs for run ID: {run_id}")
    with dependencies.db_session() as db:
        get_run_or_404(db, run_id)
        logs = _get_run_logs(db, run_id)
        return JSONResponse(content=[serialize_run_log(log) for log in logs])

@router.get("/runs/{run_id}/events")
def get_run_events(run_id: int):
    LOGGER.info(f"Retrieving events for run ID: {run_id}")
    with dependencies.db_session() as db:
        get_run_or_404(db, run_id)
        events = _get_run_events(db, run_id)
        return JSONResponse(content=[serialize_run_event(event) for event in events])


@router.post("/runs/{run_id}/events")
def add_run_event(run_id: int, event: RunEventIn):
    LOGGER.info(f"Recording event for run ID: {run_id}")
    with dependencies.db_session() as db:
        db_event = svc_add_run_event(
            db,
            run_id,
            event.type,
            event.payload,
            event.level,
            event.category,
            event.source,
            event.message,
        )
        return JSONResponse(content=serialize_run_event(db_event))


@router.post("/runs/{run_id}/logs")
def add_run_log(run_id: int, log: RunLogIn):
    LOGGER.info(f"Recording log line for run ID: {run_id}")
    with dependencies.db_session() as db:
        db_log = svc_add_run_log(db, run_id, log.stream, log.level, log.line, log.section)
        return JSONResponse(content=serialize_run_log(db_log))
    

@router.get("/runs/package/{package_id}")
def get_runs_by_package(package_id: int):
    LOGGER.info(f"Retrieving runs for package ID: {package_id}")
    with dependencies.db_session() as db:
        runs = svc_list_runs_by_package(db, package_id)
        return JSONResponse(content=[serialize_run(run) for run in runs])



