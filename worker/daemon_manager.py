"""
Daemon Manager for Crucible AI Agents
Handles long-running daemon containers with health monitoring and restart policies.

Security model:
- Uses docker-proxy (tecnativa/docker-socket-proxy) for restricted API access
- Daemon containers run on separate network (crucibleaiagents-daemon) isolated from platform
- Worker only has access to: CONTAINERS (inspect, list), POST (create, start), DELETE (remove)
"""

import os
import json
import subprocess
import re
import uuid
from typing import Optional, Dict, List
from datetime import datetime, timezone
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.orm import Session

# Import API modules
import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.utils.logger import get_logger, log_event, log_exception
from api.utils.db import SessionLocal

STORAGE_DIR = os.getenv("STORAGE_DIR", "/workspace/package/deployed")
WORKSPACE_PACKAGE_HOST_PATH = os.getenv("WORKSPACE_PACKAGE_HOST_PATH", "")
DOCKER_NETWORK = os.getenv("AGENTFLOW_DOCKER_NETWORK", "crucibleaiagents_default")
DAEMON_DOCKER_NETWORK = os.getenv("AGENTFLOW_DAEMON_DOCKER_NETWORK", "crucibleaiagents-daemon")
RUNNER_IMAGE = os.getenv("RUNNER_IMAGE", "crucibleaiagents-runner:latest")
API_BASE_URL = os.getenv("RUNNER_API_BASE_URL", "http://api:8000")
DAEMON_API_BASE_URL = os.getenv("DAEMON_API_BASE_URL", "http://host.docker.internal:8080")
DOCKER_HOST = os.getenv("DOCKER_HOST", "tcp://docker-proxy:2375")

LOGGER = get_logger("worker.daemon_manager")


@contextmanager
def db_session() -> Session:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _utc_now():
    return datetime.now(timezone.utc)


def get_daemon_run_info(run_id: int) -> Optional[Dict]:
    """Get daemon run information from database."""
    with db_session() as db:
        row = db.execute(text("""
            SELECT r.id, r.agent_package_id, r.timeout_seconds, r.container_id, r.restart_count,
                   ap.storage_path, ap.health_check_config,
                   ap.restart_policy, ap.expoded_port
            FROM runs r
            JOIN agent_packages ap ON ap.id = r.agent_package_id
            WHERE r.id = :run_id AND r.runtime_mode = 'daemon'
        """), {"run_id": run_id}).fetchone()
        
        if not row:
            return None
        
        return {
            "id": row[0],
            "package_id": row[1],
            "timeout_seconds": row[2],
            "container_id": row[3],
            "restart_count": row[4],
            "storage_path": row[5],
            "health_check_config": json.loads(row[6]) if row[6] else {},
            "restart_policy": row[7] or "on-failure",
            "exposed_port": row[8],
        }


def get_active_daemon_runs() -> List[Dict]:
    """Get all active daemon runs from database."""
    with db_session() as db:
        rows = db.execute(text("""
            SELECT r.id, r.agent_package_id, r.container_id, r.last_health_check, r.restart_count,
                   ap.storage_path, ap.health_check_config, ap.restart_policy,
                 ap.expoded_port
            FROM runs r
            JOIN agent_packages ap ON ap.id = r.agent_package_id
            WHERE r.runtime_mode = 'daemon' 
              AND r.status IN ('running', 'starting')
              AND COALESCE(ap.disabled, false) = false
        """)).fetchall()
        
        result = []
        for row in rows:
            result.append({
                "id": row[0],
                "package_id": row[1],
                "container_id": row[2],
                "last_health_check": row[3],
                "restart_count": row[4],
                "storage_path": row[5],
                "health_check_config": json.loads(row[6]) if row[6] else {},
                "restart_policy": row[7] or "on-failure",
                "exposed_port": row[8],
            })
        return result


def update_daemon_run(run_id: int, **kwargs) -> None:
    """Update daemon run fields. Uses ORM to prevent SQL injection."""
    allowed_columns = {"status", "container_id", "restart_count", "last_health_check", 
                      "exit_code", "error", "stopped_at", "completed_at", "exposed_port"}
    unknown = set(kwargs) - allowed_columns
    if unknown:
        raise ValueError(f"update_daemon_run: disallowed column(s): {unknown}")

    if not kwargs:
        return

    with db_session() as db:
        from api.schemas.model import Runs
        db.query(Runs).filter(Runs.id == run_id).update(kwargs, synchronize_session=False)


def check_container_status(container_id: str) -> Optional[Dict]:
    """Check if container exists and is running. Returns status dict or None if not found."""
    try:
        cmd = [
            "docker", "--host", DOCKER_HOST,
            "inspect", container_id,
            "--format", "{{json .State}}",
        ]
        result = subprocess.run(cmd, shell=False, capture_output=True, text=True, timeout=5)

        if result.returncode != 0:
            log_event(
                LOGGER, 30, "daemon.container.not_found",
                "Container not found in Docker inspect",
                container_id=container_id[:12],
            )
            return None

        state_json = (result.stdout or "").strip()
        state = json.loads(state_json)
        
        return {
            "running": state.get("Running", False),
            "exit_code": state.get("ExitCode", -1),
            "error": state.get("Error", ""),
        }
    except Exception as e:
        log_exception(LOGGER, "daemon.container.inspect_error", "Failed to inspect container", container_id=container_id[:12])
        return None


def perform_health_check(exposed_port: Optional[int], health_endpoint: str = "/health") -> bool:
    """Perform HTTP health check on daemon endpoint."""
    if not exposed_port:
        return True  # No health check configured
    
    try:
        import socket
        sock = socket.create_connection(("localhost", exposed_port), timeout=2)
        sock.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def should_restart(restart_policy: str, exit_code: int, restart_count: int, max_restarts: int = 5) -> bool:
    """Determine if daemon should be restarted based on policy."""
    if restart_count >= max_restarts:
        log_event(LOGGER, 30, "daemon.restart.max_attempts", "Max restart attempts reached", restart_count=restart_count)
        return False
    
    if restart_policy == "always":
        return True
    elif restart_policy == "on-failure":
        return exit_code != 0
    elif restart_policy == "never":
        return False
    
    return False


def map_storage_path_to_runner_path(storage_path: str) -> str:
    """Map API storage path to runner-visible path."""
    if not storage_path:
        raise ValueError("storage_path is empty")
    
    normalized = storage_path.strip()
    
    # Canonical path in containers: /workspace/package/deployed/<dir>
    if normalized.startswith("/workspace/package/"):
        return normalized
    
    # Host path form: .../package/deployed/<dir>
    if "package" in normalized and "deployed" in normalized:
        parts = normalized.split("deployed")
        if len(parts) > 1:
            rel = parts[1].lstrip("/")
            return f"/workspace/package/deployed/{rel}"
    
    # Fallback
    return f"/workspace/package/deployed/{os.path.basename(normalized)}"


def load_package_secret_environment(package_id: int) -> Dict[str, str]:
    """Load decrypted package secrets as daemon container env variables."""
    with db_session() as db:
        rows = db.execute(
            text("""
                SELECT key_name, encrypted_value
                FROM package_secrets
                WHERE package_id = :package_id
            """),
            {"package_id": package_id},
        ).fetchall()
        secret_pairs = [
            (str(row.key_name or "").strip(), str(row.encrypted_value or "").strip())
            for row in rows
        ]

    if not secret_pairs:
        return {}

    try:
        from api.utils.secrets_manager import get_secrets_manager
        decryptor = get_secrets_manager()
    except Exception:
        log_event(
            LOGGER,
            30,
            "daemon.secrets_manager_unavailable",
            "Secrets manager unavailable; skipping secret env injection",
            package_id=package_id,
        )
        return {}

    resolved: Dict[str, str] = {}

    for key_name, encrypted_value in secret_pairs:
        if not key_name or not encrypted_value:
            continue
        try:
            resolved[key_name] = decryptor.decrypt(encrypted_value)
        except Exception:
            log_event(
                LOGGER,
                30,
                "daemon.secret_decrypt_failed",
                "Failed to decrypt package secret; skipping key",
                package_id=package_id,
                key_name=key_name,
            )

    return resolved


def start_daemon_container(run_info: Dict) -> tuple[str, Optional[int]]:
    """Start daemon container with proper isolation and security.

    Returns: (container_id, exposed_port)
    """
    run_id = run_info["id"]
    package_id = run_info["package_id"]
    storage_path = run_info["storage_path"]
    exposed_port = run_info.get("exposed_port")

    container_name = f"daemon-pkg{package_id}-run{run_id}-{uuid.uuid4().hex[:8]}"
    runner_path = map_storage_path_to_runner_path(storage_path)

    # Build docker run command
    runner_api_token = (
        os.getenv("AGENTFLOW_RUNNER_API_TOKEN")
        or os.getenv("AGENTFLOW_API_TOKEN")
        or os.getenv("API_TOKEN", "")
    )

    cmd = [
        "docker", "--host", DOCKER_HOST,
        "run", "-d",
        "--name", container_name,
        "--network", DAEMON_DOCKER_NETWORK,
        # Ensure detached daemon containers are not grouped under compose services.
        "--label", "com.crucible.daemon=true",
        "--label", "com.docker.compose.project=crucible-detached-daemon",
        "--label", "com.docker.compose.service=crucible-daemon-runtime",
        "--label", "com.docker.compose.version=manual",
        "-e", f"RUN_ID={run_id}",
        "-e", f"API_BASE_URL={DAEMON_API_BASE_URL}",
        "-e", f"PACKAGE_DIR={runner_path}",
        "-v", f"{WORKSPACE_PACKAGE_HOST_PATH}:/workspace/package",
    ]

    if runner_api_token:
        cmd.extend(["-e", f"AGENTFLOW_API_TOKEN={runner_api_token}"])

    secret_env = run_info.get("secret_env") if isinstance(run_info.get("secret_env"), dict) else None
    if secret_env is None:
        secret_env = load_package_secret_environment(package_id)

    # Add secrets with validation
    secret_count = 0
    for key_name, value in secret_env.items():
        if key_name and value:
            cmd.extend(["-e", f"{key_name}={value}"])
            secret_count += 1

    if secret_count > 0:
        log_event(
            LOGGER, 20, "daemon.secrets.injected",
            "Secrets injected into daemon container environment",
            run_id=run_id, package_id=package_id,
            secret_count=secret_count,
        )
    elif secret_env:
        log_event(
            LOGGER, 30, "daemon.secrets.none_injected",
            "Secret env was present but no valid key/value pairs were injected",
            run_id=run_id, package_id=package_id,
        )

    # Add port mapping if exposed_port configured
    if exposed_port and 1 <= exposed_port <= 65535:
        cmd.extend(["-p", f"{exposed_port}:{exposed_port}"])

    # Add health check if configured
    health_config = run_info.get("health_check_config", {})
    if health_config and health_config.get("enabled"):
        interval = health_config.get("interval", "30s")
        timeout = health_config.get("timeout", "5s")
        path = health_config.get("path", "/health")
        cmd.extend([
            "--health-cmd", f"curl -f http://localhost:{exposed_port or 8000}{path} || exit 1",
            "--health-interval", interval,
            "--health-timeout", timeout,
            "--health-retries", "3",
        ])

    cmd.append(RUNNER_IMAGE)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            log_event(
                LOGGER, 40, "daemon.start.failed",
                "Failed to start daemon container",
                run_id=run_id, package_id=package_id,
                error=result.stderr[:200],
            )
            try:
                raise RuntimeError(f"Failed to start daemon: {result.stderr}")
            except RuntimeError:
                raise

        container_id = result.stdout.strip()

        log_event(
            LOGGER, 20, "daemon.started",
            "Daemon container started successfully",
            run_id=run_id, package_id=package_id,
            container_id=container_id[:12],
            exposed_port=exposed_port,
        )

        return container_id, exposed_port

    except Exception as e:
        log_exception(
            LOGGER, "daemon.start.exception",
            "Exception starting daemon container",
            run_id=run_id, package_id=package_id,
        )
        raise


def capture_daemon_logs(run_id: int, container_id: str, since: Optional[str] = None) -> int:
    """Capture and store daemon container logs in database.

    Args:
        run_id: The run ID for storing logs
        container_id: The Docker container ID
        since: RFC 3339 timestamp to read logs from (e.g., epoch time or timestamp)

    Returns:
        Number of log lines captured
    """
    try:
        from sqlalchemy import text

        # Build docker logs command
        cmd = ["docker", "--host", DOCKER_HOST, "logs", container_id]
        if since:
            cmd.extend(["--since", since])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

        if result.returncode != 0:
            return 0

        # Parse logs and store each line
        logs_stored = 0
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue

            # Store log line in database
            with db_session() as db:
                db.execute(text("""
                    INSERT INTO run_logs(run_id, ts, stream, level, line, section)
                    VALUES (:run_id, :ts, :stream, :level, :line, :section)
                """), {
                    "run_id": run_id,
                    "ts": _utc_now(),
                    "stream": "stdout",
                    "level": "INFO",
                    "line": line,
                    "section": "daemon",
                })
            logs_stored += 1

        if logs_stored > 0:
            log_event(
                LOGGER, 20, "daemon.logs.captured",
                "Captured daemon container logs",
                run_id=run_id,
                container_id=container_id[:12],
                log_count=logs_stored,
            )

        return logs_stored

    except Exception as e:
        log_exception(
            LOGGER, "daemon.logs.capture_error",
            "Error capturing daemon logs",
            run_id=run_id,
            container_id=container_id[:12],
        )
        return 0


def remove_daemon_container(container_id: str) -> bool:
    """Remove daemon container. Returns True if successful."""
    try:
        cmd = ["docker", "--host", DOCKER_HOST, "rm", "-f", container_id]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

        if result.returncode == 0:
            log_event(LOGGER, 20, "daemon.container.removed", "Container removed", container_id=container_id[:12])
            return True
        else:
            log_event(LOGGER, 30, "daemon.container.remove_failed", "Failed to remove container", container_id=container_id[:12])
            return False
    except Exception as e:
        log_exception(LOGGER, "daemon.container.remove_error", "Error removing container", container_id=container_id[:12])
        return False
