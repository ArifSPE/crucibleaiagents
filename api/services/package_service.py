import os
import re
import json
import shutil
import zipfile
from typing import Dict, Any, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session
from schemas.model import AgentPackage, PackageSecret
from utils import config


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
