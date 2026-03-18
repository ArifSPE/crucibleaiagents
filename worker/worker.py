#!/usr/bin/env python3
"""Worker loop for claiming and executing queued runs.

This worker is intentionally DB-driven and process-local:
- claims pending/queued runs atomically
- executes package entrypoints from extracted package directories
- stores logs/events/status in DB for API retrieval
"""

from __future__ import annotations

import os
import sys
import subprocess
import threading
import time
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

# Import API modules from repository root for stable package resolution.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.utils.logger import get_logger, log_event, log_exception  # noqa: E402
from api.utils.db import SessionLocal  # noqa: E402
from worker.daemon_manager import (  # noqa: E402
    start_daemon_container as dm_start_daemon_container,
    check_container_status as dm_check_container_status,
)

LOGGER = get_logger("worker")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "5"))
MAX_CONCURRENT_RUNS = int(os.getenv("MAX_CONCURRENT_RUNS", "10"))


@contextmanager
def db_session() -> Generator[Session, None, None]:
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


def _claim_next_run_for(deployment: Optional[str] = None) -> Optional[dict]:
    with db_session() as db:
        deployment_value = (deployment or "").strip().lower() or None
        deployment_filter_sql = ""
        if deployment_value == "local":
            deployment_filter_sql = """
              AND COALESCE(NULLIF(TRIM(LOWER(p.deployment)), ''), 'local') = 'local'
            """
        elif deployment_value == "container":
            deployment_filter_sql = """
              AND LOWER(COALESCE(p.deployment, '')) = 'container'
            """

        claim_sql = text(f"""
            SELECT r.id, r.agent_package_id, r.timeout_seconds, r.runtime_mode
            FROM runs r
            JOIN agent_packages p ON p.id = r.agent_package_id
            WHERE r.status IN ('pending', 'queued')
              AND COALESCE(p.disabled, false) = false
              {deployment_filter_sql}
            ORDER BY r.id ASC
            LIMIT 1
            FOR UPDATE SKIP LOCKED
        """)

        try:
            row = db.execute(claim_sql).fetchone()
        except OperationalError:
            # SQLite used in tests does not support FOR UPDATE SKIP LOCKED.
            row = db.execute(text(f"""
                SELECT r.id, r.agent_package_id, r.timeout_seconds, r.runtime_mode
                FROM runs r
                JOIN agent_packages p ON p.id = r.agent_package_id
                WHERE r.status IN ('pending', 'queued')
                  AND COALESCE(p.disabled, false) = false
                  {deployment_filter_sql}
                ORDER BY r.id ASC
                LIMIT 1
            """)).fetchone()

        if not row:
            return None

        db.execute(text("""
            UPDATE runs
            SET status = 'running', started_at = :started_at
            WHERE id = :run_id
        """), {"run_id": row.id, "started_at": _utc_now()})

        return {
            "id": row.id,
            "package_id": row.agent_package_id,
            "timeout_seconds": row.timeout_seconds,
            "runtime_mode": row.runtime_mode or "batch",
        }


def _claim_next_run() -> Optional[dict]:
    """Backward-compatible claim helper used by existing tests and mixed worker mode."""
    return _claim_next_run_for(None)


def _get_package(package_id: int) -> Optional[dict]:
    with db_session() as db:
        row = db.execute(text("""
            SELECT id, name, language, entry_point, storage_path, timeout_seconds, deployment,
                   runtime_mode, deamon_auto_restart, expoded_port
            FROM agent_packages
            WHERE id = :package_id
        """), {"package_id": package_id}).fetchone()

        if not row:
            return None

        return {
            "id": row.id,
            "name": row.name,
            "language": (row.language or "python").strip().lower(),
            "entry_point": row.entry_point,
            "storage_path": row.storage_path,
            "timeout_seconds": row.timeout_seconds,
            "deployment": "container" if str(row.deployment or "").strip().lower() == "container" else "local",
            "runtime_mode": str(row.runtime_mode or "batch").strip().lower(),
            "daemon_auto_start": bool(row.deamon_auto_restart),
            "exposed_port": row.expoded_port,
        }


def _enqueue_autostart_daemon_runs(deployment: Optional[str]) -> int:
    deployment_value = (deployment or "").strip().lower()
    deployment_filter_sql = ""
    if deployment_value == "local":
        deployment_filter_sql = """
          AND COALESCE(NULLIF(TRIM(LOWER(deployment)), ''), 'local') = 'local'
        """
    elif deployment_value == "container":
        deployment_filter_sql = """
          AND LOWER(COALESCE(deployment, '')) = 'container'
        """

    created = 0
    with db_session() as db:
        packages = db.execute(text(f"""
            SELECT id, timeout_seconds
            FROM agent_packages
            WHERE runtime_mode = 'daemon'
              AND COALESCE(deamon_auto_restart, false) = true
              AND COALESCE(disabled, false) = false
              {deployment_filter_sql}
        """)).fetchall()

        for pkg in packages:
            existing = db.execute(text("""
                SELECT id, status, container_id
                FROM runs
                WHERE agent_package_id = :package_id
                  AND runtime_mode = 'daemon'
                  AND status IN ('pending', 'queued', 'running')
                LIMIT 1
            """), {"package_id": pkg.id}).fetchone()
            if existing:
                # Recover stale running daemon runs where DB says running but container is gone.
                if deployment_value == "container" and existing.status == "running":
                    container_id = str(existing.container_id or "").strip()
                    container_state = dm_check_container_status(container_id) if container_id else None
                    if not container_state or not container_state.get("running", False):
                        db.execute(text("""
                            UPDATE runs
                            SET status = 'failed',
                                error = :error,
                                completed_at = :completed_at
                            WHERE id = :run_id
                        """), {
                            "run_id": existing.id,
                            "error": "Recovered stale daemon run (container not running)",
                            "completed_at": _utc_now(),
                        })
                        log_event(
                            LOGGER,
                            logging.WARNING,
                            "worker.daemon_stale_run_recovered",
                            "Recovered stale daemon run during autostart",
                            package_id=pkg.id,
                            run_id=existing.id,
                            container_id=container_id or None,
                        )
                    else:
                        continue
                else:
                    continue

            db.execute(text("""
                INSERT INTO runs(agent_package_id, status, timeout_seconds, runtime_mode, restart_count)
                VALUES (:package_id, 'queued', :timeout_seconds, 'daemon', 0)
            """), {
                "package_id": pkg.id,
                "timeout_seconds": pkg.timeout_seconds or 60,
            })
            created += 1

    if created:
        log_event(
            LOGGER,
            logging.INFO,
            "worker.daemon_autostart_runs_enqueued",
            "Enqueued daemon auto-start runs",
            created=created,
            deployment=deployment_value or "all",
        )
    return created


def _insert_event(run_id: int, event_type: str, level: str = "INFO", category: str = "system", source: str = "worker", message: Optional[str] = None, payload: Optional[dict] = None):
    with db_session() as db:
        db.execute(text("""
            INSERT INTO run_events(run_id, ts, type, level, category, source, message, payload_jason)
            VALUES (:run_id, :ts, :type, :level, :category, :source, :message, :payload)
        """), {
            "run_id": run_id,
            "ts": _utc_now(),
            "type": event_type,
            "level": level,
            "category": category,
            "source": source,
            "message": message,
            "payload": str(payload or {}),
        })


def _insert_log(run_id: int, stream: str, line: str, level: str = "INFO", section: Optional[str] = None):
    with db_session() as db:
        db.execute(text("""
            INSERT INTO run_logs(run_id, ts, stream, level, line, section)
            VALUES (:run_id, :ts, :stream, :level, :line, :section)
        """), {
            "run_id": run_id,
            "ts": _utc_now(),
            "stream": stream,
            "level": level,
            "line": line,
            "section": section,
        })


def _update_run(run_id: int, status: str, exit_code: Optional[int] = None, error: Optional[str] = None):
    with db_session() as db:
        db.execute(text("""
            UPDATE runs
            SET status = :status,
                exit_code = :exit_code,
                error = :error,
                completed_at = :completed_at
            WHERE id = :run_id
        """), {
            "run_id": run_id,
            "status": status,
            "exit_code": exit_code,
            "error": error,
            "completed_at": _utc_now(),
        })


def _set_run_container_info(run_id: int, container_id: Optional[str] = None, exposed_port: Optional[int] = None):
    with db_session() as db:
        db.execute(text("""
            UPDATE runs
            SET container_id = :container_id,
                exposed_port = :exposed_port
            WHERE id = :run_id
        """), {
            "run_id": run_id,
            "container_id": container_id,
            "exposed_port": exposed_port,
        })


def _resolve_workspace(storage_path: Optional[str]) -> Path:
    if storage_path:
        p = Path(storage_path)
        if p.exists():
            return p

        # When API runs in Docker it persists /workspace/... paths. If local
        # worker runs on host, remap that prefix to REPO_ROOT-relative paths.
        raw = str(storage_path).strip()
        workspace_prefix = "/workspace/"
        if raw.startswith(workspace_prefix):
            host_candidate = REPO_ROOT / raw[len(workspace_prefix):]
            if host_candidate.exists():
                return host_candidate

    # Prefer STORAGE_DIR env var (set in docker-compose for the worker container)
    storage_dir = os.getenv("STORAGE_DIR")
    if storage_dir:
        return Path(storage_dir)

    # Last-resort local default (repo root / package / deployed)
    default_dir = Path(__file__).resolve().parent.parent / "package" / "deployed"
    return default_dir


def _resolve_entrypoint(language: str, workspace: Path, configured: Optional[str]) -> Path:
    if configured:
        candidate = workspace / configured
        if candidate.exists() and candidate.is_file():
            return candidate

    defaults = {
        "python": ["src/agent.py", "main.py", "agent.py"],
        "typescript": ["src/agent.ts", "index.ts"],
        "node.js": ["src/agent.js", "index.js"],
    }

    for item in defaults.get(language, ["src/agent.py"]):
        candidate = workspace / item
        if candidate.exists() and candidate.is_file():
            return candidate

    raise FileNotFoundError(f"No entrypoint found for language={language} workspace={workspace}")


def _command_for(language: str, entrypoint: Path) -> list[str]:
    if language == "python":
        return [sys.executable, str(entrypoint)]
    if language == "typescript":
        return ["npx", "ts-node", str(entrypoint)]
    if language == "node.js":
        return ["node", str(entrypoint)]
    raise ValueError(f"Unsupported language: {language}")


def _stream_output(run_id: int, stream_name: str, stream):
    try:
        for line in iter(stream.readline, ""):
            if not line:
                break
            clean = line.rstrip("\n")
            if clean:
                level = "ERROR" if stream_name == "stderr" else "INFO"
                _insert_log(run_id, stream_name, clean, level=level, section="agent")
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _execute_local(run_id: int, package: dict, workspace: Path, timeout_seconds: Optional[int]) -> None:
    entrypoint = _resolve_entrypoint(package["language"], workspace, package.get("entry_point"))
    cmd = _command_for(package["language"], entrypoint)

    _insert_event(run_id, "worker.run_start", message="Local run execution started", payload={"cmd": cmd})

    child_env = os.environ.copy()
    child_env.setdefault("RUN_ID", str(run_id))
    child_env.setdefault(
        "API_BASE_URL",
        os.getenv("RUNNER_API_BASE_URL") or os.getenv("API_BASE_URL") or "http://localhost:8080",
    )

    process = subprocess.Popen(
        cmd,
        cwd=str(workspace),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=child_env,
    )

    threads = [
        threading.Thread(target=_stream_output, args=(run_id, "stdout", process.stdout), daemon=True),
        threading.Thread(target=_stream_output, args=(run_id, "stderr", process.stderr), daemon=True),
    ]
    for t in threads:
        t.start()

    try:
        rc = process.wait(timeout=timeout_seconds or None)
    except subprocess.TimeoutExpired:
        process.kill()
        _insert_event(run_id, "worker.run_timeout", level="ERROR", message="Local run timed out")
        _update_run(run_id, "failed", exit_code=124, error="Run timed out")
        return

    for t in threads:
        t.join(timeout=2)

    if rc == 0:
        _insert_event(run_id, "worker.run_complete", message="Local run execution completed", payload={"exit_code": rc})
        _update_run(run_id, "completed", exit_code=rc, error=None)
    else:
        _insert_event(run_id, "worker.run_failed", level="ERROR", message="Local run execution failed", payload={"exit_code": rc})
        _update_run(run_id, "failed", exit_code=rc, error=f"Process exited with code {rc}")


def _execute_container(run_id: int, package: dict, workspace: Path, timeout_seconds: Optional[int]) -> None:
    runner_image = os.getenv("RUNNER_IMAGE", "crucibleaiagents-runner:latest")
    api_base_url = os.getenv("RUNNER_API_BASE_URL", os.getenv("API_BASE_URL", "http://localhost:8000"))
    container_name = f"agent-run-{run_id}-{uuid.uuid4().hex[:8]}"

    workspace_mount = str(workspace)
    host_workspace_root = os.getenv("WORKSPACE_HOST_PATH")
    host_package_root = os.getenv("WORKSPACE_PACKAGE_HOST_PATH")
    if host_package_root and workspace_mount.startswith("/workspace/package"):
        suffix = workspace_mount[len("/workspace/package"):]
        workspace_mount = f"{host_package_root.rstrip('/')}{suffix}"
    if host_workspace_root and workspace_mount.startswith("/workspace/"):
        workspace_mount = f"{host_workspace_root.rstrip('/')}/{workspace_mount[len('/workspace/'):]}"

    cmd = [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        "-e",
        f"RUN_ID={run_id}",
        "-e",
        f"API_BASE_URL={api_base_url}",
        "-e",
        "PACKAGE_DIR=/workspace/code",
        "-v",
        f"{workspace_mount}:/workspace/code",
        runner_image,
    ]

    _set_run_container_info(run_id, container_id=container_name, exposed_port=None)
    _insert_event(
        run_id,
        "worker.run_start",
        message="Container run execution started",
        payload={"image": runner_image, "container_name": container_name},
    )

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ.copy(),
    )

    threads = [
        threading.Thread(target=_stream_output, args=(run_id, "stdout", process.stdout), daemon=True),
        threading.Thread(target=_stream_output, args=(run_id, "stderr", process.stderr), daemon=True),
    ]
    for t in threads:
        t.start()

    try:
        rc = process.wait(timeout=timeout_seconds or None)
    except subprocess.TimeoutExpired:
        process.kill()
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, text=True)
        _insert_event(run_id, "worker.run_timeout", level="ERROR", message="Container run timed out")
        _update_run(run_id, "failed", exit_code=124, error="Container run timed out")
        _set_run_container_info(run_id, container_id=None, exposed_port=None)
        return

    for t in threads:
        t.join(timeout=2)

    _set_run_container_info(run_id, container_id=None, exposed_port=None)

    if rc == 0:
        _insert_event(run_id, "worker.run_complete", message="Container run execution completed", payload={"exit_code": rc})
        _update_run(run_id, "completed", exit_code=rc, error=None)
    else:
        _insert_event(run_id, "worker.run_failed", level="ERROR", message="Container run execution failed", payload={"exit_code": rc})
        _update_run(run_id, "failed", exit_code=rc, error=f"Container process exited with code {rc}")


def _execute_container_daemon(run_id: int, package: dict, run: dict, workspace: Path) -> None:
    """Execute daemon container using docker-proxy for security.
    
    Daemon containers:
    - Run detached (-d) and stay running
    - Execute on separate daemon network (crucibleaiagents-daemon)
    - Use restricted docker-proxy socket (limited API operations)
    - Are monitored by daemon_monitor for health checks and restarts
    """
    try:
        # Build run_info dict for daemon_manager
        exposed_port = package.get("exposed_port")
        try:
            exposed_port = int(exposed_port) if exposed_port is not None else None
        except (TypeError, ValueError):
            exposed_port = None
        
        run_info = {
            "id": run_id,
            "package_id": package.get("id"),
            # Keep full package storage path so daemon runner can resolve manifest reliably.
            "storage_path": package.get("storage_path") or str(workspace),
            "exposed_port": exposed_port,
            "health_check_config": package.get("health_check_config", {}),
            "restart_policy": package.get("restart_policy", "on-failure"),
            "timeout_seconds": package.get("timeout_seconds", 60),
        }
        
        _insert_event(
            run_id,
            "worker.daemon_starting",
            message="Starting daemon container (uses docker-proxy security)",
            payload={"exposed_port": exposed_port, "restart_policy": run_info["restart_policy"]},
        )
        
        # Use daemon_manager to start container securely
        container_id, final_exposed_port = dm_start_daemon_container(run_info)
        
        # Update run with container info
        _set_run_container_info(run_id, container_id=container_id, exposed_port=final_exposed_port)
        
        _insert_event(
            run_id,
            "worker.daemon_started",
            message="Daemon container started successfully",
            payload={
                "container_id": container_id[:12],
                "exposed_port": final_exposed_port,
                "monitoring_enabled": True,
            },
        )
        
    except Exception as e:
        error_msg = str(e)[:200]
        _insert_event(
            run_id,
            "worker.daemon_start_failed",
            level="ERROR",
            message="Failed to start daemon container",
            payload={"error": error_msg},
        )
        _update_run(run_id, "failed", exit_code=1, error=error_msg)
        raise


def _execute_run(run: dict):
    run_id = run["id"]
    package = _get_package(run["package_id"])

    if not package:
        _update_run(run_id, "failed", exit_code=1, error="Package not found")
        return

    try:
        workspace = _resolve_workspace(package.get("storage_path"))

        # Defensive fallback: if resolution lands on the generic deployed root,
        # try deriving the package-specific folder from storage_path basename.
        storage_path_raw = str(package.get("storage_path") or "").strip()
        if storage_path_raw and workspace.name == "deployed":
            derived_name = Path(storage_path_raw).name
            if derived_name:
                derived_workspace = workspace / derived_name
                if derived_workspace.exists() and derived_workspace.is_dir():
                    workspace = derived_workspace

        # Additional defensive fallback: if still on generic deployed dir,
        # try package-specific folders by convention.
        if workspace.name == "deployed":
            candidate_names = [
                f"{package.get('name')}_pkg{package.get('id')}",
                str(package.get("name") or ""),
            ]
            for candidate_name in candidate_names:
                if not candidate_name:
                    continue
                candidate_workspace = workspace / candidate_name
                if candidate_workspace.exists() and candidate_workspace.is_dir():
                    workspace = candidate_workspace
                    break

        if not workspace.exists():
            raise FileNotFoundError(f"Workspace not found: {workspace}")

        # If the extracted package has one nested root folder, use it.
        children = list(workspace.iterdir())
        if len(children) == 1 and children[0].is_dir() and (children[0] / "manifest.json").exists():
            workspace = children[0]

        run_mode = str(run.get("runtime_mode") or package.get("runtime_mode") or "batch").strip().lower()
        timeout_seconds = run.get("timeout_seconds") or package.get("timeout_seconds")

        if run_mode == "daemon":
            if package.get("deployment") == "container":
                _execute_container_daemon(run_id, package, run, workspace)
            else:
                _insert_event(
                    run_id,
                    "worker.daemon_unsupported_deployment",
                    level="ERROR",
                    message="Daemon mode is only supported for container deployment",
                )
                _update_run(run_id, "failed", exit_code=1, error="Daemon mode unsupported for local deployment")
            return

        if package.get("deployment") == "container":
            _execute_container(run_id, package, workspace, timeout_seconds)
        else:
            _execute_local(run_id, package, workspace, timeout_seconds)

    except Exception as exc:
        _insert_event(run_id, "worker.run_exception", level="ERROR", message=str(exc))
        _update_run(run_id, "failed", exit_code=1, error=str(exc))


def main():
    _enqueue_autostart_daemon_runs(None)
    log_event(
        LOGGER,
        logging.INFO,
        "worker.startup",
        "Worker started",
        poll_seconds=POLL_SECONDS,
        max_concurrent_runs=MAX_CONCURRENT_RUNS,
    )
    executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_RUNS, thread_name_prefix="agent-run")
    try:
        while True:
            try:
                run = _claim_next_run_for(None)
            except Exception as exc:
                log_exception(LOGGER, "worker.claim_error", "Error claiming next run", error=str(exc))
                time.sleep(POLL_SECONDS)
                continue

            if not run:
                time.sleep(POLL_SECONDS)
                continue

            executor.submit(_execute_run, run)
            # Small sleep to avoid tight-loop when many runs are queued
            time.sleep(0.1)
    except KeyboardInterrupt:
        log_event(LOGGER, logging.INFO, "worker.shutdown", "Worker stopped")
    finally:
        executor.shutdown(wait=True, cancel_futures=False)


if __name__ == "__main__":
    main()
