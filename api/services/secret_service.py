import json
from typing import Any
from fastapi import HTTPException
from schemas.model import PackageSecret, AgentPackage, PackageSchedule
from services.schedule_service import _calculate_next_run_time
from services.package_service import (
    _get_missing_required_secret_keys_for_package,
    _refresh_package_secret_metadata,
)
from utils.secrets_manager import get_secrets_manager
from utils.logger import get_logger, log_event

LOGGER = get_logger("api.services.secret_service")


def serialize_secret(secret: PackageSecret) -> dict:
    return {
        "id": secret.id,
        "package_id": secret.package_id,
        "key_name": secret.key_name,
        "created_at": secret.created_at.isoformat() if secret.created_at else None,
        "updated_at": secret.updated_at.isoformat() if secret.updated_at else None,
    }


def get_package_or_404(db: Any, package_id: int) -> AgentPackage:
    pkg = db.query(AgentPackage).filter(AgentPackage.id == package_id).first()
    if not pkg:
        log_event(LOGGER, 30, "secret.package_not_found", "Package not found while handling secret", package_id=package_id)
        raise HTTPException(status_code=404, detail="Package not found")
    return pkg


def get_secret_or_404(db: Any, package_id: int, secret_id: int) -> PackageSecret:
    secret = db.query(PackageSecret).filter(
        PackageSecret.id == secret_id,
        PackageSecret.package_id == package_id,
    ).first()
    if not secret:
        log_event(LOGGER, 30, "secret.not_found", "Secret not found", package_id=package_id, secret_id=secret_id)
        raise HTTPException(status_code=404, detail="Secret not found")
    return secret


def list_secrets(db: Any, package_id: int) -> list[PackageSecret]:
    get_package_or_404(db, package_id)
    secrets = db.query(PackageSecret).filter(
        PackageSecret.package_id == package_id
    ).order_by(PackageSecret.key_name).all()
    log_event(LOGGER, 20, "secret.listed", "Listed package secrets", package_id=package_id, secret_count=len(secrets))
    return secrets


def _reconcile_package_secret_state(db: Any, package: AgentPackage) -> list[str]:
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


def create_or_update_secret(db: Any, package_id: int, key_name: str, value: str) -> tuple[PackageSecret, bool, list[str]]:
    pkg = get_package_or_404(db, package_id)
    log_event(LOGGER, 20, "secret.create_or_update.start", "Creating or updating package secret", package_id=package_id, key_name=key_name)

    try:
        encrypted = get_secrets_manager().encrypt(value)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=f"Encryption error: {exc}")

    existing = db.query(PackageSecret).filter(
        PackageSecret.package_id == package_id,
        PackageSecret.key_name == key_name,
    ).first()
    if existing:
        existing.encrypted_value = encrypted
        missing_secret_keys = _reconcile_package_secret_state(db, pkg)
        db.commit()
        db.refresh(existing)
        log_event(
            LOGGER,
            20,
            "secret.updated",
            "Updated package secret",
            package_id=package_id,
            secret_id=existing.id,
            key_name=existing.key_name,
            missing_secret_keys_count=len(missing_secret_keys),
        )
        return existing, False, missing_secret_keys

    secret = PackageSecret(
        package_id=package_id,
        key_name=key_name,
        encrypted_value=encrypted,
    )
    db.add(secret)

    missing_secret_keys = _reconcile_package_secret_state(db, pkg)
    db.commit()
    db.refresh(secret)
    log_event(
        LOGGER,
        20,
        "secret.created",
        "Created package secret",
        package_id=package_id,
        secret_id=secret.id,
        key_name=secret.key_name,
        missing_secret_keys_count=len(missing_secret_keys),
    )
    return secret, True, missing_secret_keys


def update_secret(db: Any, package_id: int, secret_id: int, key_name: str, value: str) -> tuple[PackageSecret, list[str]]:
    secret = get_secret_or_404(db, package_id, secret_id)

    if key_name != secret.key_name:
        conflict = db.query(PackageSecret).filter(
            PackageSecret.package_id == package_id,
            PackageSecret.key_name == key_name,
            PackageSecret.id != secret_id,
        ).first()
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=f"Secret '{key_name}' already exists for this package.",
            )

    try:
        encrypted = get_secrets_manager().encrypt(value)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=f"Encryption error: {exc}")

    secret.key_name = key_name
    secret.encrypted_value = encrypted

    pkg = get_package_or_404(db, package_id)
    missing_secret_keys = _reconcile_package_secret_state(db, pkg)
    db.commit()
    db.refresh(secret)
    log_event(
        LOGGER,
        20,
        "secret.updated",
        "Updated package secret by id",
        package_id=package_id,
        secret_id=secret.id,
        key_name=secret.key_name,
        missing_secret_keys_count=len(missing_secret_keys),
    )
    return secret, missing_secret_keys


def delete_secret(db: Any, package_id: int, secret_id: int) -> tuple[str, list[str]]:
    secret = get_secret_or_404(db, package_id, secret_id)
    key_name = secret.key_name
    db.delete(secret)

    pkg = get_package_or_404(db, package_id)
    missing_secret_keys = _reconcile_package_secret_state(db, pkg)
    db.commit()
    log_event(
        LOGGER,
        20,
        "secret.deleted",
        "Deleted package secret",
        package_id=package_id,
        secret_id=secret_id,
        key_name=key_name,
        missing_secret_keys_count=len(missing_secret_keys),
    )
    return key_name, missing_secret_keys
