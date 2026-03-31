#!/usr/bin/env python3
"""
Package Watcher Service

Monitors an incoming directory for new package zip files. When a package appears:
1. Validates it's a .zip file with manifest.json
2. Registers manifest metadata with the AgentFlow API
3. Moves it to the deployed directory on success
4. Moves it to failed directory on error

This enables automatic package deployment by simply copying files to the incoming directory.
"""

import logging
import os
import sys
import time
import shutil
import zipfile
import json
import urllib.error
import urllib.request
from pathlib import Path
from datetime import datetime
from importlib import import_module
from typing import Optional, Dict, Any
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure watcher picks values from repository-level .env when run directly.
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _load_logger_module():
    for module_name in ("shared.logger", "shared.shared.logger"):
        try:
            return import_module(module_name)
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError(
        "Unable to import shared logger module. Install dependencies with `pip install -r requirements.txt`."
    )


_LOGGER_MODULE = _load_logger_module()
get_logger = _LOGGER_MODULE.get_logger
log_event = _LOGGER_MODULE.log_event
log_exception = _LOGGER_MODULE.log_exception

_LOGGER = get_logger("watcher.package")


BASE_DIR = os.getenv('PACKAGE_WATCHER_BASE_DIR', str(Path(__file__).parent.parent))
INCOMING_DIR = os.getenv('PACKAGE_WATCHER_INCOMING_DIR', os.path.join(BASE_DIR, 'incoming'))
DEPLOYED_DIR = os.getenv('PACKAGE_WATCHER_DEPLOYED_DIR', os.path.join(BASE_DIR, 'deployed'))
FAILED_DIR = os.getenv('PACKAGE_WATCHER_FAILED_DIR', os.path.join(BASE_DIR, 'failed'))
ARCHIVES_DIR = os.getenv('PACKAGE_WATCHER_ARCHIVES_DIR', os.path.join(BASE_DIR, 'archives'))
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8080")
API_TOKEN = os.getenv("API_TOKEN") or os.getenv("AGENTFLOW_API_TOKEN")
POLL_INTERVAL = int(os.getenv("WATCHER_POLL_INTERVAL", "5"))  # seconds

def _ensure_watcher_directories() -> None:
    """Create watcher directories, falling back to local project paths if needed."""
    global BASE_DIR, INCOMING_DIR, DEPLOYED_DIR, FAILED_DIR, ARCHIVES_DIR

    try:
        os.makedirs(INCOMING_DIR, exist_ok=True)
        os.makedirs(DEPLOYED_DIR, exist_ok=True)
        os.makedirs(FAILED_DIR, exist_ok=True)
        os.makedirs(ARCHIVES_DIR, exist_ok=True)
        return
    except OSError as e:
        # Common local failure when .env points to Docker-only /packages mount.
        if e.errno not in (13, 30):
            raise

    fallback_base = str(PROJECT_ROOT / "package")
    BASE_DIR = fallback_base
    INCOMING_DIR = os.path.join(BASE_DIR, "incoming")
    DEPLOYED_DIR = os.path.join(BASE_DIR, "deployed")
    FAILED_DIR = os.path.join(BASE_DIR, "failed")
    ARCHIVES_DIR = os.path.join(BASE_DIR, "archives")

    os.makedirs(INCOMING_DIR, exist_ok=True)
    os.makedirs(DEPLOYED_DIR, exist_ok=True)
    os.makedirs(FAILED_DIR, exist_ok=True)
    os.makedirs(ARCHIVES_DIR, exist_ok=True)

    log_event(
        _LOGGER,
        logging.WARNING,
        "watcher.path_fallback",
        "Configured watcher paths were not writable; using local project package directories",
        base_dir=BASE_DIR,
    )


_ensure_watcher_directories()


def _extract_secret_keys(manifest: Dict[str, Any]) -> list[str]:
    secret_keys: set[str] = set()

    raw_secrets = manifest.get("secrets")
    if isinstance(raw_secrets, list):
        for item in raw_secrets:
            if isinstance(item, str) and item.strip():
                secret_keys.add(item.strip())

    environment = manifest.get("environment")
    if isinstance(environment, dict):
        for value in environment.values():
            if not isinstance(value, str):
                continue
            if value.startswith("{secrets.") and value.endswith("}"):
                key = value[len("{secrets."):-1].strip()
                if key:
                    secret_keys.add(key)

    return sorted(secret_keys)


def _extract_schedule_data(manifest: Dict[str, Any]) -> tuple[Optional[bool], Optional[str], Optional[Dict[str, Any]]]:
    schedule_enabled = None
    schedule_type = None
    schedule_config: Dict[str, Any] = {}

    schedule = manifest.get("schedule")
    if isinstance(schedule, dict):
        if isinstance(schedule.get("enabled"), bool):
            schedule_enabled = schedule.get("enabled")
        if isinstance(schedule.get("type"), str) and schedule.get("type").strip():
            schedule_type = schedule.get("type").strip().lower()

        if schedule.get("interval_seconds") is not None:
            schedule_config["interval_seconds"] = schedule.get("interval_seconds")
        cron_expr = schedule.get("cron_expr") or schedule.get("cron_expression")
        if cron_expr:
            schedule_config["cron_expr"] = cron_expr
        if schedule.get("timestamp") is not None:
            schedule_config["timestamp"] = schedule.get("timestamp")
        if schedule.get("timezone") is not None:
            schedule_config["timezone"] = schedule.get("timezone")

    if isinstance(manifest.get("schedule_enabled"), bool):
        schedule_enabled = manifest.get("schedule_enabled")

    top_level_cron = manifest.get("schedule_cron")
    if top_level_cron:
        schedule_type = schedule_type or "cron"
        schedule_config["cron_expr"] = top_level_cron

    if schedule_type is None:
        if "cron_expr" in schedule_config:
            schedule_type = "cron"
        elif "interval_seconds" in schedule_config:
            schedule_type = "interval"

    return schedule_enabled, schedule_type, (schedule_config or None)


def _normalize_upload_action(raw_action: Any) -> str:
    action = str(raw_action or "new").strip().lower()
    action_map = {
        "new": "new",
        "update": "update",
        "new_version": "new_version",
        "new-version": "new_version",
        "newversion": "new_version",
    }
    return action_map.get(action, "new")


def _normalize_runtime_mode(raw_runtime_mode: Any) -> str:
    return "daemon" if str(raw_runtime_mode or "").strip().lower() == "daemon" else "batch"


def _normalize_deployment(raw_deployment: Any) -> str:
    return "container" if str(raw_deployment or "").strip().lower() == "container" else "local"

def validate_package(zip_path: str) -> tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """
    Validate that the file is a valid package.
    
    Returns:
        (is_valid, error_message, manifest_dict)
    """
    # Check if it's a zip file
    if not zip_path.endswith(".zip"):
        return False, "Not a .zip file", None
    
    # Check if file is readable
    if not os.path.isfile(zip_path):
        return False, "File not found or not readable", None
    
    # Try to open as zip
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            # Check for manifest.json
            manifest_candidates = [name for name in archive.namelist() if name.endswith("manifest.json")]
            if not manifest_candidates:
                return False, "No manifest.json found in package", None
            
            # Read manifest
            manifest_name = sorted(manifest_candidates, key=len)[0]
            with archive.open(manifest_name) as manifest_file:
                manifest = json.loads(manifest_file.read().decode("utf-8"))
                
            return True, None, manifest
    except zipfile.BadZipFile:
        return False, "Invalid or corrupted zip file", None
    except json.JSONDecodeError:
        return False, "Invalid JSON in manifest.json", None
    except Exception as e:
        return False, f"Validation error: {str(e)}", None

def extract_package_to_deployed(zip_path: str, package_name: str, package_id: int) -> tuple[bool, Optional[str]]:
    """
    Extract package to deployed directory for execution.
    
    Returns:
        (success, error_message)
    """
    try:
        # Create package directory name: packagename_pkgID
        safe_package_name = "".join(c if c.isalnum() or c in ('-', '_', '.') else '_' for c in package_name)
        package_dir_name = f"{safe_package_name}_pkg{package_id}"
        extracted_path = os.path.join(DEPLOYED_DIR, package_dir_name)
        
        # Remove existing directory if it exists
        if os.path.exists(extracted_path):
            shutil.rmtree(extracted_path)
        
        os.makedirs(extracted_path, exist_ok=True)
        
        # Extract zip file
        with zipfile.ZipFile(zip_path, "r") as archive:
            extracted_root_abs = os.path.abspath(extracted_path)
            # Security check: reject symlinks and path traversal
            for info in archive.infolist():
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    return False, f"Security: Archive member is a symlink: {info.filename}"
                member_path = os.path.abspath(os.path.normpath(os.path.join(extracted_path, info.filename)))
                if not member_path.startswith(extracted_root_abs + os.sep) and member_path != extracted_root_abs:
                    return False, f"Security: Archive member attempts path traversal: {info.filename}"

            archive.extractall(extracted_path)
        
        log_event(_LOGGER, logging.INFO, "watcher.package_extracted",
                  "Package extracted to deployed directory", package_dir=package_dir_name)
        return True, None
        
    except zipfile.BadZipFile:
        return False, "Invalid or corrupted zip file during extraction"
    except Exception as e:
        return False, f"Extraction error: {str(e)}"


def move_to_archives(zip_path: str, package_id: int):
    """Move successfully deployed package zip to archives directory"""
    filename = os.path.basename(zip_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archived_filename = f"{timestamp}_pkg{package_id}_{filename}"
    archived_path = os.path.join(ARCHIVES_DIR, archived_filename)
    
    shutil.move(zip_path, archived_path)
    log_event(_LOGGER, logging.INFO, "watcher.package_archived",
              "Package zip archived", package_id=package_id, filename=archived_filename)


def move_to_failed(zip_path: str, error_reason: str):
    """Move failed package to failed directory with error log"""
    filename = os.path.basename(zip_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    failed_filename = f"{timestamp}_FAILED_{filename}"
    failed_path = os.path.join(FAILED_DIR, failed_filename)
    
    shutil.move(zip_path, failed_path)
    
    # Create error log file
    error_log_path = failed_path.replace(".zip", ".error.txt")
    with open(error_log_path, "w") as f:
        f.write(f"Failed at: {datetime.now().isoformat()}\n")
        f.write(f"Reason: {error_reason}\n")
    
    log_event(_LOGGER, logging.ERROR, "watcher.package_failed",
              "Package moved to failed directory", filename=failed_filename, reason=error_reason)


def register_package(manifest: Dict[str, Any], filename: str) -> tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """Register package metadata in API without uploading the package file."""
    package_name = str(manifest.get("name") or "").strip()
    if not package_name:
        return False, "Manifest must contain a non-empty 'name' field", None

    try:
        timeout_seconds = int(manifest.get("timeout_seconds") or 60)
    except (TypeError, ValueError):
        return False, "Manifest timeout_seconds must be an integer", None

    package_action = _normalize_upload_action(manifest.get("action") or manifest.get("acation"))
    runtime_mode = _normalize_runtime_mode(manifest.get("runtime_mode"))
    deployment = _normalize_deployment(manifest.get("deployment"))

    restart_policy = str(manifest.get("restart_policy") or "never").strip().lower()
    if restart_policy not in {"never", "on-failure", "always"}:
        restart_policy = "never"

    daemon_auto_start = manifest.get("daemon_auto_start")
    if daemon_auto_start is None and runtime_mode == "daemon":
        daemon_auto_start = bool(manifest.get("auto_start", False))

    exposed_port = None
    expose_cfg = manifest.get("expose")
    if isinstance(expose_cfg, dict) and expose_cfg.get("port") is not None:
        try:
            exposed_port = int(expose_cfg.get("port"))
        except (TypeError, ValueError):
            exposed_port = None

    schedule_enabled, schedule_type, schedule_config = _extract_schedule_data(manifest)
    secret_keys = _extract_secret_keys(manifest)

    manifest_metadata = {
        key: manifest.get(key)
        for key in (
            "agent_id",
            "action",
            "auto_start",
            "health_check",
            "expose",
            "dependencies",
            "tags",
            "features",
            "configuration",
            "observability",
            "webhooks",
            "websocket",
            "system_prompt",
            "error_handling",
        )
        if manifest.get(key) is not None
    }
    manifest_metadata["normalized_action"] = package_action

    payload = {
        "name": package_name,
        "version": str(manifest.get("version") or "1.0.0"),
        "description": manifest.get("description"),
        "language": manifest.get("language"),
        "entrypoint": manifest.get("entrypoint") or manifest.get("entry_point"),
        "timeout_seconds": timeout_seconds,
        "filename": filename,
        "runtime_mode": runtime_mode,
        "deployment": deployment,
        "restart_policy": restart_policy,
        "daemon_auto_start": daemon_auto_start,
        "exposed_port": exposed_port,
        "schedule_enabled": schedule_enabled,
        "schedule_type": schedule_type,
        "schedule_config": schedule_config,
        "secret_keys": secret_keys,
        "environment": manifest.get("environment"),
        "llm_provider": manifest.get("llm_provider"),
        "tool_bindings": manifest.get("tool_bindings"),
        "manifest_metadata": manifest_metadata,
    }

    request_url = f"{API_BASE_URL.rstrip('/')}/packages/register"
    request_data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Agentflow-Source": "watcher",
    }
    if API_TOKEN:
        headers["X-Agentflow-Token"] = API_TOKEN

    try:
        request = urllib.request.Request(
            request_url,
            data=request_data,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            response_body = response.read().decode("utf-8") if response else "{}"
            response_data = json.loads(response_body) if response_body else {}
            return True, None, response_data
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        return False, f"API HTTP {e.code}: {error_body}", None
    except urllib.error.URLError as e:
        return False, f"API connection error: {e.reason}", None
    except Exception as e:
        return False, f"Unexpected register error: {str(e)}", None




def process_package(zip_path: str):
    """Process a single package file"""
    filename = os.path.basename(zip_path)
    log_event(_LOGGER, logging.INFO, "watcher.package_processing",
              "Processing incoming package", filename=filename)

    # Validate package
    is_valid, error_msg, manifest = validate_package(zip_path)
    if not is_valid:
        log_event(_LOGGER, logging.ERROR, "watcher.package_validation_failed",
                  "Package validation failed", filename=filename, error=error_msg)
        move_to_failed(zip_path, f"Validation failed: {error_msg}")
        return

    package_name = manifest.get("name", filename)
    log_event(_LOGGER, logging.INFO, "watcher.package_valid",
              "Package validated successfully",
              filename=filename, package_name=package_name,
              language=manifest.get("language", "unknown"))

    # Register metadata in API (no package-byte upload)
    success, error_msg, response_data = register_package(manifest, filename)
    if not success:
        log_event(_LOGGER, logging.ERROR, "watcher.package_register_failed",
                  "Package registration failed", filename=filename, error=error_msg)
        move_to_failed(zip_path, f"Registration failed: {error_msg}")
        return

    package_id = response_data.get("id")
    if not isinstance(package_id, int):
        log_event(_LOGGER, logging.ERROR, "watcher.package_register_invalid_response",
                  "Package registration response missing valid id", filename=filename, response=response_data)
        move_to_failed(zip_path, "Registration failed: API response missing package id")
        return

    log_event(_LOGGER, logging.INFO, "watcher.package_registered",
              "Package metadata registered successfully",
              filename=filename, package_id=package_id, package_name=package_name)

    # Extract package to deployed directory
    success, error_msg = extract_package_to_deployed(zip_path, package_name, package_id)
    if not success:
        log_event(_LOGGER, logging.ERROR, "watcher.package_extract_failed",
                  "Package extraction failed", filename=filename, error=error_msg)
        move_to_failed(zip_path, f"Extraction failed: {error_msg}")
        return

    log_event(_LOGGER, logging.INFO, "watcher.package_ready",
              "Package extracted and ready for execution",
              package_id=package_id, package_name=package_name)

    # Archive the original zip file
    move_to_archives(zip_path, package_id)



def scan_incoming_directory():
    """Scan incoming directory for new packages"""
    try:
        files = [f for f in os.listdir(INCOMING_DIR) if f.endswith(".zip")]
        
        if not files:
            return

        log_event(_LOGGER, logging.INFO, "watcher.scan_found",
                  "Found packages to process", count=len(files))

        for filename in sorted(files):
            zip_path = os.path.join(INCOMING_DIR, filename)

            # Check if file is still being written (size changing)
            initial_size = os.path.getsize(zip_path)
            time.sleep(0.5)
            if os.path.getsize(zip_path) != initial_size:
                log_event(_LOGGER, logging.INFO, "watcher.file_skipped",
                          "Skipping file still being written", filename=filename)
                continue

            try:
                process_package(zip_path)
            except Exception as e:
                log_event(_LOGGER, logging.ERROR, "watcher.package_process_error",
                          "Unhandled error processing package", filename=filename, error=str(e))
                try:
                    move_to_failed(zip_path, f"Processing error: {str(e)}")
                except Exception as move_error:
                    log_event(_LOGGER, logging.ERROR, "watcher.move_failed",
                              "Failed to move errored file to failed directory",
                              filename=filename, error=str(move_error))

    except Exception as e:
        log_event(_LOGGER, logging.ERROR, "watcher.scan_error",
                  "Error scanning incoming directory", error=str(e))


def main():
    """Main watcher loop"""
    log_event(_LOGGER, logging.INFO, "watcher.startup",
              "AgentFlow Package Watcher started",
              packages_root=BASE_DIR,
              incoming_dir=INCOMING_DIR,
              deployed_dir=DEPLOYED_DIR,
              archives_dir=ARCHIVES_DIR,
              failed_dir=FAILED_DIR,
              api_base_url=API_BASE_URL,
              poll_interval_seconds=POLL_INTERVAL,
              api_token_set=bool(API_TOKEN),
              mode="docker" if os.path.exists("/packages") else "local")

    if not API_TOKEN:
        log_event(_LOGGER, logging.ERROR, "watcher.startup_failed",
                  "API token is not set; set API_TOKEN or AGENTFLOW_API_TOKEN")
        sys.exit(1)

    log_event(_LOGGER, logging.INFO, "watcher.watching",
              "Watching for packages", incoming_dir=INCOMING_DIR)

    try:
        while True:
            scan_incoming_directory()
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        log_event(_LOGGER, logging.INFO, "watcher.shutdown", "Watcher shutting down")
        sys.exit(0)
    except Exception as e:
        log_event(_LOGGER, logging.ERROR, "watcher.fatal_error",
                  "Fatal error in watcher loop", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    print("Starting AgentFlow Package Watcher...")
    main()
