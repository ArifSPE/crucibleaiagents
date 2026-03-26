import os
import re
import json
import shutil
import zipfile
from typing import Dict, Any, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session
from schemas.model import AgentPackage, PackageSecret, PackageSchedule
from utils import config
from services.schedule_service import _calculate_next_run_time
from services.run_service import _to_utc_iso


def _normalize_language(language: Optional[str]) -> str:
    """Normalize manifest language values to stable API values."""
    if not language:
        return "python"

    normalized = str(language).strip().lower()
    language_map = {
        "python": "python",
        "py": "python",
        "node": "node.js",
        "nodejs": "node.js",
        "node.js": "node.js",
        "javascript": "node.js",
        "js": "node.js",
        "typescript": "typescript",
        "ts": "typescript",
    }
    return language_map.get(normalized, normalized)


def _normalize_upload_action(raw_action: Optional[str]) -> str:
    """Normalize manifest upload action to supported values."""
    action = (raw_action or "new").strip().lower()
    action_map = {
        "new": "new",
        "update": "update",
        "new_version": "new_version",
        "new-version": "new_version",
        "newversion": "new_version",
    }
    normalized = action_map.get(action)
    if not normalized:
        raise HTTPException(
            status_code=400,
            detail="Invalid manifest action. Supported values: new, update, new_version",
        )
    return normalized


def _extract_manifest_from_zip(package_path: str) -> Dict[str, Any]:
    """Read manifest.json from uploaded package zip, if present."""
    try:
        with zipfile.ZipFile(package_path, "r") as archive:
            manifest_candidates = [name for name in archive.namelist() if name.endswith("manifest.json")]
            if not manifest_candidates:
                return {}

            manifest_name = sorted(manifest_candidates, key=len)[0]
            with archive.open(manifest_name) as manifest_file:
                return json.loads(manifest_file.read().decode("utf-8"))
    except Exception:
        return {}


def _extract_package_to_deployed(zip_path: str, package_name: str, package_id: int) -> str:
    """
    Extract package to deployed directory.

    Args:
        zip_path: Path to the zip file
        package_name: Name of the package
        package_id: Package ID from database

    Returns:
        Path to extracted package directory
    """
    # Create safe directory name
    safe_name = "".join(c if c.isalnum() or c in ('-', '_', '.') else '_' for c in package_name)
    package_dir_name = f"{safe_name}_pkg{package_id}"
    extracted_path = os.path.join(config.STORAGE_DIR, package_dir_name)

    # Remove existing directory if it exists
    if os.path.exists(extracted_path):
        shutil.rmtree(extracted_path)

    os.makedirs(extracted_path, exist_ok=True)

    # Extract with security checks
    with zipfile.ZipFile(zip_path, "r") as archive:
        for info in archive.infolist():
            # Reject symlinks (Unix attr stored in external_attr upper 16 bits)
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f"Security: Archive member is a symlink: {info.filename}")
            # Reject path traversal attempts
            member_path = os.path.normpath(os.path.join(extracted_path, info.filename))
            if not member_path.startswith(os.path.abspath(extracted_path) + os.sep) and member_path != os.path.abspath(extracted_path):
                raise ValueError(f"Security: Archive member attempts path traversal: {info.filename}")
        archive.extractall(extracted_path)

    return extracted_path


def _extract_secret_placeholders(manifest: Dict[str, Any]) -> set:
    """Extract `{secrets.KEY}` placeholder keys from manifest environment values."""
    environment = manifest.get("environment")
    if not isinstance(environment, dict):
        return set()

    secret_keys: set = set()
    for value in environment.values():
        if not isinstance(value, str):
            continue

        if value.startswith("{secrets.") and value.endswith("}"):
            key_name = value[len("{secrets."):-1].strip()
            if key_name:
                secret_keys.add(key_name)

    return secret_keys


def _get_missing_required_secret_keys(db: Session, package_id: int, manifest: Dict[str, Any]) -> list:
    """Return required secret keys (from manifest placeholders) that are missing values."""
    required_keys = _extract_secret_placeholders(manifest)
    if not required_keys:
        return []

    secret_rows = db.query(PackageSecret).filter(PackageSecret.package_id == package_id).all()
    key_to_value = {row.key_name: row.encrypted_value for row in secret_rows}

    missing = []
    for key_name in required_keys:
        value = key_to_value.get(key_name)
        if value is None or str(value).strip() == "":
            missing.append(key_name)

    return sorted(missing)


def _get_required_secret_keys_from_package(package: AgentPackage) -> list[str]:
    """Return normalized required secret keys declared in package metadata."""
    metadata = package.description_json if isinstance(package.description_json, dict) else {}
    raw_keys = metadata.get("secret_keys", [])
    if not isinstance(raw_keys, list):
        return []

    normalized = {
        str(key).strip()
        for key in raw_keys
        if isinstance(key, str) and str(key).strip()
    }
    return sorted(normalized)


def _get_missing_required_secret_keys_for_package(db: Session, package: AgentPackage) -> list[str]:
    """Return required secret keys that do not have values for a package."""
    required_keys = _get_required_secret_keys_from_package(package)
    if not required_keys:
        return []

    secret_rows = db.query(PackageSecret).filter(PackageSecret.package_id == package.id).all()
    key_to_value = {row.key_name: row.encrypted_value for row in secret_rows}

    missing = []
    for key_name in required_keys:
        value = key_to_value.get(key_name)
        if value is None or str(value).strip() == "":
            missing.append(key_name)

    return sorted(missing)


def _refresh_package_secret_metadata(package: AgentPackage, missing_secret_keys: list[str]) -> Dict[str, Any]:
    """Refresh package metadata flags driven by required secret readiness."""
    metadata: Dict[str, Any] = dict(package.description_json) if isinstance(package.description_json, dict) else {}

    requested_schedule_enabled = metadata.get("schedule_requested_enabled")
    if requested_schedule_enabled is None:
        requested_schedule_enabled = bool(package.schedule_enables)

    normalized_missing = sorted({str(key).strip() for key in missing_secret_keys if str(key).strip()})

    metadata["schedule_requested_enabled"] = bool(requested_schedule_enabled)
    metadata["missing_secret_keys"] = normalized_missing
    metadata["schedule_activation_blocked"] = bool(normalized_missing and requested_schedule_enabled)

    package.description_json = metadata
    return metadata


def _normalize_deployment(raw: Any) -> str:
    return "container" if str(raw or "").strip().lower() == "container" else "local"


def _safe_package_dir_name(package_name: str, package_id: int) -> str:
    safe_name = "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in package_name)
    return f"{safe_name}_pkg{package_id}"


def _build_storage_path(package_name: str, package_id: int) -> str:
    return os.path.join(config.STORAGE_DIR, _safe_package_dir_name(package_name, package_id))


def serialize_package(pkg: AgentPackage) -> dict:
    metadata = pkg.description_json if isinstance(pkg.description_json, dict) else {}
    return {
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
        "secret_keys": metadata.get("secret_keys", []),
        "schedule_requested_enabled": metadata.get("schedule_requested_enabled"),
        "schedule_activation_blocked": metadata.get("schedule_activation_blocked", False),
        "missing_secret_keys": metadata.get("missing_secret_keys", []),
        "disabled": pkg.disabled,
        "runtime_mode": pkg.runtime_mode,
        "deployment": _normalize_deployment(pkg.deployment),
        "restart_policy": pkg.restart_policy,
        "daemon_auto_start": pkg.deamon_auto_restart,
        "exposed_port": pkg.expoded_port,
    }


def list_packages(db: Session) -> list[AgentPackage]:
    return db.query(AgentPackage).all()


def get_package_or_404(db: Session, package_id: int) -> AgentPackage:
    pkg = db.query(AgentPackage).filter(AgentPackage.id == package_id).first()
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    return pkg


def register_package(db: Session, payload: Any) -> tuple[AgentPackage, bool, str, int, list[str], bool]:
    package_name = (payload.name or "").strip()
    package_version = (payload.version or "").strip()

    if not package_name:
        raise HTTPException(status_code=400, detail="Package name is required")
    if not package_version:
        raise HTTPException(status_code=400, detail="Package version is required")

    manifest_metadata = payload.manifest_metadata if isinstance(payload.manifest_metadata, dict) else {}
    explicit_action = manifest_metadata.get("normalized_action") or manifest_metadata.get("action")
    package_action = _normalize_upload_action(explicit_action) if explicit_action else "upsert"

    package = db.query(AgentPackage).filter(AgentPackage.name == package_name).first()
    if package_action == "new" and package is not None:
        raise HTTPException(status_code=400, detail=f"Package with name '{package_name}' already exists")
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

    package.storage_path = _build_storage_path(package.name, package.id)

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

        db.add(PackageSecret(package_id=package.id, key_name=normalized_key, encrypted_value=""))
        provisioned_secret_keys += 1

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

    if payload.schedule_type and payload.schedule_config:
        next_run_time = _calculate_next_run_time(payload.schedule_type, payload.schedule_config)
        existing_schedule = db.query(PackageSchedule).filter(PackageSchedule.package_id == package.id).first()

        if existing_schedule:
            existing_schedule.schedule_type = payload.schedule_type
            existing_schedule.schedule_config = json.dumps(payload.schedule_config)
            existing_schedule.is_active = effective_schedule_enabled
            existing_schedule.next_run_time = next_run_time
        else:
            db.add(
                PackageSchedule(
                    package_id=package.id,
                    schedule_type=payload.schedule_type,
                    schedule_config=json.dumps(payload.schedule_config),
                    is_active=effective_schedule_enabled,
                    next_run_time=next_run_time,
                )
            )

    db.commit()
    return (
        package,
        created,
        package_action,
        provisioned_secret_keys,
        sorted(set(missing_required_secret_keys)) if missing_required_secret_keys else [],
        effective_schedule_enabled,
    )
