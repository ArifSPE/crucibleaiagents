import logging
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from schemas.schedules import ScheduleConfig
from utils import dependency as dependencies
from services.schedule_service import _calculate_next_run_time
from services.schedule_service import (
    serialize_schedule,
    list_schedules as svc_list_schedules,
    get_schedule_or_404,
    list_schedules_for_package as svc_list_schedules_for_package,
    create_schedule as svc_create_schedule,
    update_schedule as svc_update_schedule,
    activate_schedule as svc_activate_schedule,
    deactivate_schedule as svc_deactivate_schedule,
    delete_schedule as svc_delete_schedule,
)
from utils.logger import get_logger, log_event, log_exception

router = APIRouter()
LOGGER = get_logger("api.schedules")


@router.get("/schedules")
def list_schedules():
    """List all schedules across all packages."""
    with dependencies.db_session() as db:
        schedules = svc_list_schedules(db)
        log_event(LOGGER, logging.INFO, "schedules.list", "Listed all schedules", count=len(schedules))
        return JSONResponse(content=[serialize_schedule(s) for s in schedules])


@router.get("/schedules/{schedule_id}")
def get_schedule(schedule_id: int):
    """Get a single schedule by ID."""
    with dependencies.db_session() as db:
        schedule = get_schedule_or_404(db, schedule_id)
        return JSONResponse(content=serialize_schedule(schedule))


@router.get("/packages/{package_id}/schedules")
def list_schedules_for_package(package_id: int):
    """List all schedules for a specific package."""
    with dependencies.db_session() as db:
        schedules = svc_list_schedules_for_package(db, package_id)
        return JSONResponse(content=[serialize_schedule(s) for s in schedules])


@router.post("/packages/{package_id}/schedules")
def create_schedule(package_id: int, config: ScheduleConfig):
    """Create a new schedule for a package."""
    with dependencies.db_session() as db:
        schedule = svc_create_schedule(db, package_id, config)

        log_event(LOGGER, logging.INFO, "schedule.created", "Schedule created",
                  schedule_id=schedule.id, package_id=package_id, schedule_type=config.schedule_type)
        return JSONResponse(status_code=201, content=serialize_schedule(schedule))


@router.put("/schedules/{schedule_id}")
def update_schedule(schedule_id: int, config: ScheduleConfig):
    """Update an existing schedule's type, config, and active state."""
    with dependencies.db_session() as db:
        schedule = svc_update_schedule(db, schedule_id, config)

        log_event(LOGGER, logging.INFO, "schedule.updated", "Schedule updated",
                  schedule_id=schedule_id, schedule_type=config.schedule_type)
        return JSONResponse(content=serialize_schedule(schedule))


@router.patch("/schedules/{schedule_id}/activate")
def activate_schedule(schedule_id: int):
    """Enable a schedule."""
    with dependencies.db_session() as db:
        svc_activate_schedule(db, schedule_id)
        log_event(LOGGER, logging.INFO, "schedule.activated", "Schedule activated", schedule_id=schedule_id)
        return JSONResponse(content={"id": schedule_id, "is_active": True})


@router.patch("/schedules/{schedule_id}/deactivate")
def deactivate_schedule(schedule_id: int):
    """Disable a schedule without deleting it."""
    with dependencies.db_session() as db:
        svc_deactivate_schedule(db, schedule_id)
        log_event(LOGGER, logging.INFO, "schedule.deactivated", "Schedule deactivated", schedule_id=schedule_id)
        return JSONResponse(content={"id": schedule_id, "is_active": False})


@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: int):
    """Delete a schedule permanently."""
    with dependencies.db_session() as db:
        svc_delete_schedule(db, schedule_id)
        log_event(LOGGER, logging.INFO, "schedule.deleted", "Schedule deleted", schedule_id=schedule_id)
        return JSONResponse(content={"deleted": True, "id": schedule_id})
