import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from schemas.model import AgentPackage, PackageSchedule
from utils.dependency import db_session
from schemas.schedules import ScheduleConfig
from utils.logger import get_logger, log_event, log_exception

_LOGGER = get_logger("api.startup.schedule")


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _calculate_next_run_time(schedule_type: str, schedule_config: dict, last_run_time: Optional[datetime] = None) -> Optional[datetime]:
    """Calculate the next run time for a schedule.

    Args:
        schedule_type: 'interval', 'cron', or 'at'
        schedule_config: Dict with schedule parameters
        last_run_time: When the schedule last ran (None for first calculation)

    Returns:
        datetime of next run, or None if can't calculate
    """
    now = datetime.now(timezone.utc)

    if schedule_type == "interval":
        # For interval, next run is last_run_time + interval_seconds, or now + interval_seconds for first run
        interval_seconds = schedule_config.get("interval_seconds", 3600)
        if last_run_time:
            return _as_utc(last_run_time) + timedelta(seconds=interval_seconds)
        else:
            return now + timedelta(seconds=interval_seconds)

    elif schedule_type == "cron":
        # For cron, try to use croniter if available, otherwise set next run to now + 1 minute
        cron_expr = schedule_config.get("cron_expr", "0 0 * * *")
        try:
            from croniter import croniter
            cron = croniter(cron_expr, now)
            next_run = cron.get_next(datetime)
            return _as_utc(next_run)
        except ImportError:
            # croniter not available, just schedule for next hour
            return now + timedelta(hours=1)
        except:
            # Invalid cron expression, skip
            return None

    elif schedule_type == "at":
        # For 'at' schedule, use the timestamp provided
        timestamp_str = schedule_config.get("timestamp")
        if timestamp_str:
            try:
                scheduled_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                scheduled_time = _as_utc(scheduled_time)
                if scheduled_time > now:
                    return scheduled_time
                else:
                    return None  # Scheduled time is in the past
            except:
                return None

    return None


def _build_schedule_payload(config: ScheduleConfig) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "type": config.type,
        "enabled": bool(config.enabled),
    }
    if config.interval_seconds is not None:
        payload["interval_seconds"] = config.interval_seconds
    if config.cron_expr:
        payload["cron_expr"] = config.cron_expr
    if config.timestamp:
        payload["timestamp"] = config.timestamp
    if config.timeout_seconds is not None:
        payload["timeout_seconds"] = config.timeout_seconds
    return payload


def _load_scheduled_packages():
    """Load all active scheduled packages on API startup."""
    try:
        with db_session() as db:
            schedules = db.query(PackageSchedule).filter(PackageSchedule.is_active == True).all()

            loaded_count = 0
            for schedule in schedules:
                try:
                    # Parse schedule config
                    config = json.loads(schedule.schedule_config)

                    # If next_run_time is not set, calculate it
                    if schedule.next_run_time is None:
                        next_run = _calculate_next_run_time(
                            schedule.schedule_type,
                            config,
                            schedule.last_run_time
                        )
                        if next_run:
                            schedule.next_run_time = next_run
                            loaded_count += 1
                    else:
                        loaded_count += 1

                    # Log the schedule
                    pkg = db.query(AgentPackage).filter(AgentPackage.id == schedule.package_id).first()
                    pkg_name = pkg.filename if pkg else f"package_{schedule.package_id}"

                    log_event(_LOGGER, logging.INFO, "startup.schedule_loaded",
                              "Active schedule loaded",
                              schedule_id=schedule.id,
                              package_name=pkg_name,
                              schedule_type=schedule.schedule_type,
                              next_run_time=schedule.next_run_time.isoformat() if schedule.next_run_time else None)

                except Exception as e:
                    log_event(_LOGGER, logging.WARNING, "startup.schedule_load_failed",
                              "Failed to load schedule",
                              schedule_id=schedule.id, error=str(e))

            # Commit any changes to next_run_time
            db.commit()

            log_event(_LOGGER, logging.INFO, "startup.schedules_loaded",
                      "Active schedules loaded", count=loaded_count)

    except Exception as e:
        log_exception(_LOGGER, "startup.schedules_load_error",
                      "Error loading scheduled packages", error=str(e))
