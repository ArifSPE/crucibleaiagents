import json
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from schemas.model import PackageSchedule, AgentPackage
from schemas.schedules import ScheduleConfig
from utils import dependency as dependencies
from services.schedule_service import _calculate_next_run_time
from utils.logger import get_logger, log_event, log_exception

router = APIRouter()
LOGGER = get_logger("api.schedules")


def _schedule_to_dict(s: PackageSchedule) -> dict:
    return {
        "id": s.id,
        "package_id": s.package_id,
        "schedule_type": s.schedule_type,
        "schedule_config": s.schedule_config,
        "is_active": s.is_active,
        "last_run_time": s.last_run_time.isoformat() if s.last_run_time else None,
        "next_run_time": s.next_run_time.isoformat() if s.next_run_time else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


@router.get("/schedules")
def list_schedules():
    """List all schedules across all packages."""
    with dependencies.db_session() as db:
        schedules = db.query(PackageSchedule).order_by(PackageSchedule.id.desc()).all()
        log_event(LOGGER, logging.INFO, "schedules.list", "Listed all schedules", count=len(schedules))
        return JSONResponse(content=[_schedule_to_dict(s) for s in schedules])


@router.get("/schedules/{schedule_id}")
def get_schedule(schedule_id: int):
    """Get a single schedule by ID."""
    with dependencies.db_session() as db:
        schedule = db.query(PackageSchedule).filter(PackageSchedule.id == schedule_id).first()
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")
        return JSONResponse(content=_schedule_to_dict(schedule))


@router.get("/packages/{package_id}/schedules")
def list_schedules_for_package(package_id: int):
    """List all schedules for a specific package."""
    with dependencies.db_session() as db:
        pkg = db.query(AgentPackage).filter(AgentPackage.id == package_id).first()
        if not pkg:
            raise HTTPException(status_code=404, detail="Package not found")
        schedules = db.query(PackageSchedule).filter(
            PackageSchedule.package_id == package_id
        ).order_by(PackageSchedule.id.desc()).all()
        return JSONResponse(content=[_schedule_to_dict(s) for s in schedules])


@router.post("/packages/{package_id}/schedules")
def create_schedule(package_id: int, config: ScheduleConfig):
    """Create a new schedule for a package."""
    with dependencies.db_session() as db:
        pkg = db.query(AgentPackage).filter(AgentPackage.id == package_id).first()
        if not pkg:
            raise HTTPException(status_code=404, detail="Package not found")

        schedule_config_json = json.dumps(config.model_dump(exclude_none=True))
        next_run_time = _calculate_next_run_time(config.schedule_type, config.model_dump(exclude_none=True))

        schedule = PackageSchedule(
            package_id=package_id,
            schedule_type=config.schedule_type,
            schedule_config=schedule_config_json,
            is_active=config.enabled if config.enabled is not None else True,
            next_run_time=next_run_time,
        )
        db.add(schedule)
        db.commit()
        db.refresh(schedule)

        log_event(LOGGER, logging.INFO, "schedule.created", "Schedule created",
                  schedule_id=schedule.id, package_id=package_id, schedule_type=config.schedule_type)
        return JSONResponse(status_code=201, content=_schedule_to_dict(schedule))


@router.put("/schedules/{schedule_id}")
def update_schedule(schedule_id: int, config: ScheduleConfig):
    """Update an existing schedule's type, config, and active state."""
    with dependencies.db_session() as db:
        schedule = db.query(PackageSchedule).filter(PackageSchedule.id == schedule_id).first()
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")

        schedule.schedule_type = config.schedule_type
        schedule.schedule_config = json.dumps(config.model_dump(exclude_none=True))
        schedule.is_active = config.enabled if config.enabled is not None else schedule.is_active
        schedule.next_run_time = _calculate_next_run_time(
            config.schedule_type, config.model_dump(exclude_none=True), schedule.last_run_time
        )
        db.commit()
        db.refresh(schedule)

        log_event(LOGGER, logging.INFO, "schedule.updated", "Schedule updated",
                  schedule_id=schedule_id, schedule_type=config.schedule_type)
        return JSONResponse(content=_schedule_to_dict(schedule))


@router.patch("/schedules/{schedule_id}/activate")
def activate_schedule(schedule_id: int):
    """Enable a schedule."""
    with dependencies.db_session() as db:
        schedule = db.query(PackageSchedule).filter(PackageSchedule.id == schedule_id).first()
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")
        schedule.is_active = True
        db.commit()
        log_event(LOGGER, logging.INFO, "schedule.activated", "Schedule activated", schedule_id=schedule_id)
        return JSONResponse(content={"id": schedule_id, "is_active": True})


@router.patch("/schedules/{schedule_id}/deactivate")
def deactivate_schedule(schedule_id: int):
    """Disable a schedule without deleting it."""
    with dependencies.db_session() as db:
        schedule = db.query(PackageSchedule).filter(PackageSchedule.id == schedule_id).first()
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")
        schedule.is_active = False
        db.commit()
        log_event(LOGGER, logging.INFO, "schedule.deactivated", "Schedule deactivated", schedule_id=schedule_id)
        return JSONResponse(content={"id": schedule_id, "is_active": False})


@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: int):
    """Delete a schedule permanently."""
    with dependencies.db_session() as db:
        schedule = db.query(PackageSchedule).filter(PackageSchedule.id == schedule_id).first()
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")
        db.delete(schedule)
        db.commit()
        log_event(LOGGER, logging.INFO, "schedule.deleted", "Schedule deleted", schedule_id=schedule_id)
        return JSONResponse(content={"deleted": True, "id": schedule_id})
