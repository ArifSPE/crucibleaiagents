import json
import logging
import os
from typing import Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from schemas.model import AgentPackage, PackageSecret, PackageSchedule
from utils import config
from utils import dependency as dependencies

#from middleware.auth import _is_watcher_request
from services.package_service import (
    _normalize_language,
    _normalize_upload_action,
    _extract_manifest_from_zip,
    _extract_package_to_deployed,
    _extract_secret_placeholders,
    _get_missing_required_secret_keys,
)
from services.schedule_service import _calculate_next_run_time
from services.run_service import _to_utc_iso
from schemas.packages import PackageDisableUpdate, PackageRegisterRequest
from utils.logger import get_logger, log_event, log_exception

router = APIRouter()
LOGGER = get_logger("api.packages")


def _normalize_deployment(raw: Any) -> str:
    return "container" if str(raw or "").strip().lower() == "container" else "local"


def _safe_package_dir_name(package_name: str, package_id: int) -> str:
    safe_name = "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in package_name)
    return f"{safe_name}_pkg{package_id}"


def _build_storage_path(package_name: str, package_id: int) -> str:
    return os.path.join(config.STORAGE_DIR, _safe_package_dir_name(package_name, package_id))


@router.get("/packages")
async def list_packages():
    LOGGER.info("Listing all packages")
    with dependencies.db_session() as db:
        pkgs = db.query(AgentPackage).all()
        return JSONResponse(content=[{
            "id": pkg.id,
            "created_at": _to_utc_iso(pkg.created_at),
            "filename": pkg.filename,
            "name": pkg.name,
            "version": pkg.version,
            "description": pkg.description,
            "language": pkg.language,
            "entrypoint": pkg.entry_point,
            "timeout_seconds": pkg.timeout_seconds,
            "schedule_enabled": pkg.schedule_enables,
            "schedule_type": pkg.schedule_type,
            "schedule_config": pkg.schedule_congig,
            "llm_provider_id": None,
            "secret_keys": (
                pkg.description_json.get("secret_keys", [])
                if isinstance(pkg.description_json, dict)
                else []
            ),
            "schedule_requested_enabled": (
                pkg.description_json.get("schedule_requested_enabled")
                if isinstance(pkg.description_json, dict)
                else None
            ),
            "schedule_activation_blocked": (
                pkg.description_json.get("schedule_activation_blocked", False)
                if isinstance(pkg.description_json, dict)
                else False
            ),
            "missing_secret_keys": (
                pkg.description_json.get("missing_secret_keys", [])
                if isinstance(pkg.description_json, dict)
                else []
            ),
            "disabled": pkg.disabled,
            "runtime_mode": pkg.runtime_mode,
            "deployment": _normalize_deployment(pkg.deployment),
            "restart_policy": pkg.restart_policy,
            "daemon_auto_start": pkg.deamon_auto_restart,
            "exposed_port": pkg.expoded_port,
        } for pkg in pkgs])
    
@router.get("/packages/{package_id}")
def get_package(package_id: int):
    LOGGER.info(f"Retrieving package with ID: {package_id}")
    with dependencies.db_session() as db:
        pkg = db.query(AgentPackage).filter(AgentPackage.id == package_id).first()
        if not pkg:
            raise HTTPException(status_code=404, detail="Package not found")
        return JSONResponse(content={
            "id": pkg.id,
            "created_at": _to_utc_iso(pkg.created_at),
            "filename": pkg.filename,
            "name": pkg.name,
            "version": pkg.version,
            "description": pkg.description,
            "language": pkg.language,
            "entrypoint": pkg.entry_point,
            "timeout_seconds": pkg.timeout_seconds,
            "schedule_enabled": pkg.schedule_enables,
            "schedule_type": pkg.schedule_type,
            "schedule_config": pkg.schedule_congig,
            "llm_provider_id": None,
            "secret_keys": (
                pkg.description_json.get("secret_keys", [])
                if isinstance(pkg.description_json, dict)
                else []
            ),
            "schedule_requested_enabled": (
                pkg.description_json.get("schedule_requested_enabled")
                if isinstance(pkg.description_json, dict)
                else None
            ),
            "schedule_activation_blocked": (
                pkg.description_json.get("schedule_activation_blocked", False)
                if isinstance(pkg.description_json, dict)
                else False
            ),
            "missing_secret_keys": (
                pkg.description_json.get("missing_secret_keys", [])
                if isinstance(pkg.description_json, dict)
                else []
            ),
            "disabled": pkg.disabled,
            "runtime_mode": pkg.runtime_mode,
            "deployment": _normalize_deployment(pkg.deployment),
            "restart_policy": pkg.restart_policy,
            "daemon_auto_start": pkg.deamon_auto_restart,
            "exposed_port": pkg.expoded_port,
        })


@router.post("/packages/register")
def register_package(payload: PackageRegisterRequest):
    """Register package metadata without uploading zip bytes."""
    package_name = (payload.name or "").strip()
    package_version = (payload.version or "").strip()

    if not package_name:
        raise HTTPException(status_code=400, detail="Package name is required")
    if not package_version:
        raise HTTPException(status_code=400, detail="Package version is required")

    manifest_metadata = payload.manifest_metadata if isinstance(payload.manifest_metadata, dict) else {}
    explicit_action = manifest_metadata.get("normalized_action") or manifest_metadata.get("action")
    package_action = _normalize_upload_action(explicit_action) if explicit_action else "upsert"

    with dependencies.db_session() as db:
        package = db.query(AgentPackage).filter(AgentPackage.name == package_name).first()

        if package_action == "new" and package is not None:
            raise HTTPException(
                status_code=400,
                detail=f"Package with name '{package_name}' already exists",
            )
        if package_action == "update" and package is None:
            raise HTTPException(
                status_code=404,
                detail=f"Manifest action 'update' requires an existing package named '{package_name}'",
            )
        if package_action == "new_version" and package is None:
            raise HTTPException(
                status_code=404,
                detail=f"Manifest action 'new_version' requires an existing package named '{package_name}'",
            )

        created = package is None
        if created:
            package = AgentPackage(name=package_name, version=package_version)
            db.add(package)

        package.version = package_version
        package.description = payload.description
        package.language = _normalize_language(payload.language)
        package.entry_point = payload.entrypoint
        package.timeout_seconds = payload.timeout_seconds
        package.filename = payload.filename or f"{package_name}.zip"

        if payload.runtime_mode is not None:
            package.runtime_mode = payload.runtime_mode
        package.deployment = _normalize_deployment(payload.deployment)
        if payload.restart_policy is not None:
            package.restart_policy = payload.restart_policy
        if payload.daemon_auto_start is not None:
            package.deamon_auto_restart = payload.daemon_auto_start
        if payload.exposed_port is not None:
            package.expoded_port = payload.exposed_port
        if payload.schedule_enabled is not None:
            package.schedule_enables = payload.schedule_enabled
        if payload.schedule_type is not None:
            package.schedule_type = payload.schedule_type
        if payload.schedule_config is not None:
            package.schedule_congig = payload.schedule_config

        existing_metadata: dict[str, Any] = (
            package.description_json if isinstance(package.description_json, dict) else {}
        )

        metadata_updates = {
            "secret_keys": payload.secret_keys,
            "environment": payload.environment,
            "llm_provider": payload.llm_provider,
            "tool_bindings": payload.tool_bindings,
            "manifest_metadata": payload.manifest_metadata,
        }
        for key, value in metadata_updates.items():
            if value is not None:
                existing_metadata[key] = value

        if existing_metadata:
            package.description_json = existing_metadata

        db.commit()
        db.refresh(package)

        # Persist deterministic extracted package path so workers can execute from
        # the package-specific directory instead of the shared deployed root.
        package.storage_path = _build_storage_path(package.name, package.id)

        # Provision secret placeholders from manifest-derived key names.
        secret_keys = payload.secret_keys or []
        provisioned_secret_keys = 0
        for key_name in secret_keys:
            normalized_key = str(key_name).strip()
            if not normalized_key:
                continue
            existing_secret = db.query(PackageSecret).filter(
                PackageSecret.package_id == package.id,
                PackageSecret.key_name == normalized_key,
            ).first()
            if existing_secret:
                continue

            db.add(PackageSecret(
                package_id=package.id,
                key_name=normalized_key,
                encrypted_value="",
            ))
            provisioned_secret_keys += 1

        # Guard schedule activation until required secret values are provided.
        requested_schedule_enabled = bool(payload.schedule_enabled)
        effective_schedule_enabled = requested_schedule_enabled
        missing_required_secret_keys: list[str] = []
        if requested_schedule_enabled and secret_keys:
            for key_name in secret_keys:
                normalized_key = str(key_name).strip()
                if not normalized_key:
                    continue
                secret_row = db.query(PackageSecret).filter(
                    PackageSecret.package_id == package.id,
                    PackageSecret.key_name == normalized_key,
                ).first()
                if not secret_row or not str(secret_row.encrypted_value or "").strip():
                    missing_required_secret_keys.append(normalized_key)

            if missing_required_secret_keys:
                effective_schedule_enabled = False
                package.schedule_enables = False

        existing_metadata["schedule_requested_enabled"] = requested_schedule_enabled
        existing_metadata["schedule_activation_blocked"] = bool(missing_required_secret_keys)
        existing_metadata["missing_secret_keys"] = sorted(set(missing_required_secret_keys)) if missing_required_secret_keys else []
        package.description_json = existing_metadata

        # Upsert package schedule metadata row for scheduler subsystem.
        if payload.schedule_type and payload.schedule_config:
            next_run_time = _calculate_next_run_time(payload.schedule_type, payload.schedule_config)
            existing_schedule = db.query(PackageSchedule).filter(
                PackageSchedule.package_id == package.id
            ).first()

            if existing_schedule:
                existing_schedule.schedule_type = payload.schedule_type
                existing_schedule.schedule_config = json.dumps(payload.schedule_config)
                existing_schedule.is_active = effective_schedule_enabled
                existing_schedule.next_run_time = next_run_time
            else:
                db.add(PackageSchedule(
                    package_id=package.id,
                    schedule_type=payload.schedule_type,
                    schedule_config=json.dumps(payload.schedule_config),
                    is_active=effective_schedule_enabled,
                    next_run_time=next_run_time,
                ))

        db.commit()

        if missing_required_secret_keys:
            log_event(
                LOGGER,
                logging.WARNING,
                "package.schedule_blocked_missing_secrets",
                "Schedule activation blocked until required secrets are populated",
                package_id=package.id,
                missing_secrets=sorted(set(missing_required_secret_keys)),
            )

        log_event(
            LOGGER,
            logging.INFO,
            "package.registered",
            "Package metadata registered",
            package_id=package.id,
            package_name=package.name,
            created=created,
            action=package_action,
            schedule_enabled=effective_schedule_enabled,
            schedule_type=package.schedule_type,
            secrets_count=len(existing_metadata.get("secret_keys", [])) if isinstance(existing_metadata.get("secret_keys"), list) else 0,
            provisioned_secret_keys=provisioned_secret_keys,
        )

        return JSONResponse(
            content={
                "id": package.id,
                "name": package.name,
                "version": package.version,
                "created": created,
            }
        )
