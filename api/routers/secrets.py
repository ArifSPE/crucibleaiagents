import json
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from schemas.model import PackageSecret, AgentPackage, PackageSchedule
from utils import dependency as dependencies
from utils.secrets_manager import get_secrets_manager
from services.schedule_service import _calculate_next_run_time
from services.package_service import (
    _get_missing_required_secret_keys_for_package,
    _refresh_package_secret_metadata,
)
from utils.logger import get_logger, log_event, log_exception

router = APIRouter()
LOGGER = get_logger("api.secrets")


class SecretUpsert(BaseModel):
    key_name: str
    value: str  # plaintext — encrypted before storage, never returned


def _reconcile_package_secret_state(db, package: AgentPackage) -> list[str]:
    """Update package hold metadata and schedule activation after secret changes."""
    missing_secret_keys = _get_missing_required_secret_keys_for_package(db, package)
    metadata = _refresh_package_secret_metadata(package, missing_secret_keys)

    requested_schedule_enabled = bool(metadata.get("schedule_requested_enabled", package.schedule_enables))
    should_enable_schedule = bool(requested_schedule_enabled and not missing_secret_keys)
    package.schedule_enables = should_enable_schedule
    package.description_json = metadata

    schedules = db.query(PackageSchedule).filter(PackageSchedule.package_id == package.id).all()
    for schedule in schedules:
        schedule.is_active = should_enable_schedule
        if should_enable_schedule:
            schedule_config = {}
            if isinstance(schedule.schedule_config, str):
                try:
                    schedule_config = json.loads(schedule.schedule_config)
                except json.JSONDecodeError:
                    schedule_config = {}
            elif isinstance(schedule.schedule_config, dict):
                schedule_config = schedule.schedule_config
            schedule.next_run_time = _calculate_next_run_time(
                schedule.schedule_type,
                schedule_config,
                schedule.last_run_time,
            )

    return missing_secret_keys


def _secret_to_dict(s: PackageSecret) -> dict:
    """Return secret metadata only — never the encrypted or plaintext value."""
    return {
        "id": s.id,
        "package_id": s.package_id,
        "key_name": s.key_name,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


@router.get("/packages/{package_id}/secrets")
def list_secrets(package_id: int):
    """List secret key names for a package. Values are never returned."""
    with dependencies.db_session() as db:
        pkg = db.query(AgentPackage).filter(AgentPackage.id == package_id).first()
        if not pkg:
            raise HTTPException(status_code=404, detail="Package not found")
        secrets = db.query(PackageSecret).filter(
            PackageSecret.package_id == package_id
        ).order_by(PackageSecret.key_name).all()
        log_event(LOGGER, logging.INFO, "secrets.list", "Listed secret keys",
                  package_id=package_id, count=len(secrets))
        return JSONResponse(content=[_secret_to_dict(s) for s in secrets])


@router.get("/packages/{package_id}/secrets/{secret_id}")
def get_secret(package_id: int, secret_id: int):
    """Get secret metadata by ID. Value is never returned."""
    with dependencies.db_session() as db:
        secret = db.query(PackageSecret).filter(
            PackageSecret.id == secret_id,
            PackageSecret.package_id == package_id,
        ).first()
        if not secret:
            raise HTTPException(status_code=404, detail="Secret not found")
        return JSONResponse(content=_secret_to_dict(secret))


@router.post("/packages/{package_id}/secrets")
def create_secret(package_id: int, body: SecretUpsert):
    """Create a new secret. Value is encrypted before storage."""
    with dependencies.db_session() as db:
        pkg = db.query(AgentPackage).filter(AgentPackage.id == package_id).first()
        if not pkg:
            raise HTTPException(status_code=404, detail="Package not found")

        try:
            encrypted = get_secrets_manager().encrypt(body.value)
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=f"Encryption error: {exc}")

        existing = db.query(PackageSecret).filter(
            PackageSecret.package_id == package_id,
            PackageSecret.key_name == body.key_name,
        ).first()
        if existing:
            existing.encrypted_value = encrypted
            missing_secret_keys = _reconcile_package_secret_state(db, pkg)
            db.commit()
            db.refresh(existing)

            log_event(LOGGER, logging.INFO, "secret.updated", "Secret value updated",
                      secret_id=existing.id, package_id=package_id, key_name=body.key_name,
                      missing_secret_keys=missing_secret_keys)
            return JSONResponse(status_code=200, content=_secret_to_dict(existing))

        secret = PackageSecret(
            package_id=package_id,
            key_name=body.key_name,
            encrypted_value=encrypted,
        )
        db.add(secret)

        missing_secret_keys = _reconcile_package_secret_state(db, pkg)
        db.commit()
        db.refresh(secret)

        log_event(LOGGER, logging.INFO, "secret.created", "Secret created",
                  secret_id=secret.id, package_id=package_id, key_name=body.key_name,
                  missing_secret_keys=missing_secret_keys)
        return JSONResponse(status_code=201, content=_secret_to_dict(secret))


@router.put("/packages/{package_id}/secrets/{secret_id}")
def update_secret(package_id: int, secret_id: int, body: SecretUpsert):
    """Update key name and/or value of an existing secret. Value is re-encrypted on update."""
    with dependencies.db_session() as db:
        secret = db.query(PackageSecret).filter(
            PackageSecret.id == secret_id,
            PackageSecret.package_id == package_id,
        ).first()
        if not secret:
            raise HTTPException(status_code=404, detail="Secret not found")

        # If renaming, ensure new key name is not already taken by another record
        if body.key_name != secret.key_name:
            conflict = db.query(PackageSecret).filter(
                PackageSecret.package_id == package_id,
                PackageSecret.key_name == body.key_name,
                PackageSecret.id != secret_id,
            ).first()
            if conflict:
                raise HTTPException(
                    status_code=409,
                    detail=f"Secret '{body.key_name}' already exists for this package.",
                )

        try:
            encrypted = get_secrets_manager().encrypt(body.value)
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=f"Encryption error: {exc}")

        secret.key_name = body.key_name
        secret.encrypted_value = encrypted

        pkg = db.query(AgentPackage).filter(AgentPackage.id == package_id).first()
        if not pkg:
            raise HTTPException(status_code=404, detail="Package not found")

        missing_secret_keys = _reconcile_package_secret_state(db, pkg)
        db.commit()
        db.refresh(secret)

        log_event(LOGGER, logging.INFO, "secret.updated", "Secret updated",
                  secret_id=secret_id, package_id=package_id, key_name=body.key_name,
                  missing_secret_keys=missing_secret_keys)
        return JSONResponse(content=_secret_to_dict(secret))


@router.delete("/packages/{package_id}/secrets/{secret_id}")
def delete_secret(package_id: int, secret_id: int):
    """Delete a secret permanently."""
    with dependencies.db_session() as db:
        secret = db.query(PackageSecret).filter(
            PackageSecret.id == secret_id,
            PackageSecret.package_id == package_id,
        ).first()
        if not secret:
            raise HTTPException(status_code=404, detail="Secret not found")

        key_name = secret.key_name
        db.delete(secret)

        pkg = db.query(AgentPackage).filter(AgentPackage.id == package_id).first()
        if not pkg:
            raise HTTPException(status_code=404, detail="Package not found")

        missing_secret_keys = _reconcile_package_secret_state(db, pkg)
        db.commit()

        log_event(LOGGER, logging.INFO, "secret.deleted", "Secret deleted",
                  secret_id=secret_id, package_id=package_id, key_name=key_name,
                  missing_secret_keys=missing_secret_keys)
        return JSONResponse(content={"deleted": True, "id": secret_id})
