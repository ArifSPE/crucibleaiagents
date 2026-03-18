#!/usr/bin/env python3
import json
import os
import time
import urllib.request

import psycopg

API = "http://localhost:8080"


def post_json(path: str, payload=None):
    data = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        API + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_json(path: str):
    req = urllib.request.Request(API + path, method="GET")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def wait_for_terminal_status(run_id: int, timeout_seconds: int = 90):
    deadline = time.time() + timeout_seconds
    last = None
    while time.time() < deadline:
        run = get_json(f"/runs/{run_id}")
        last = run
        if run.get("status") in ("completed", "failed"):
            return run
        time.sleep(1)
    return last


def main() -> int:
    local_pkg = post_json(
        "/packages/register",
        {
            "name": "smoke-local",
            "version": "1.0.0",
            "language": "python",
            "entrypoint": "src/agent.py",
            "timeout_seconds": 60,
            "deployment": "local",
        },
    )
    container_pkg = post_json(
        "/packages/register",
        {
            "name": "smoke-container",
            "version": "1.0.0",
            "language": "python",
            "entrypoint": "src/agent.py",
            "timeout_seconds": 60,
            "deployment": "container",
        },
    )

    local_id = int(local_pkg["id"])
    container_id = int(container_pkg["id"])

    user = os.getenv("DB_USER", "admin")
    password = os.getenv("DB_PASSWORD", "secret123")
    dbname = os.getenv("DB_NAME", "crucibleaiagents")
    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "5432"))

    with psycopg.connect(host=host, port=port, user=user, password=password, dbname=dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE agent_packages SET storage_path=%s WHERE id=%s",
                ("/workspace/package/deployed/smoke-local", local_id),
            )
            cur.execute(
                "UPDATE agent_packages SET storage_path=%s WHERE id=%s",
                ("/workspace/package/deployed/smoke-container", container_id),
            )
        conn.commit()

    local_run = post_json(f"/runs?package_id={local_id}")
    container_run = post_json(f"/runs?package_id={container_id}")

    local_run_id = int(local_run["id"])
    container_run_id = int(container_run["id"])

    local_result = wait_for_terminal_status(local_run_id)
    container_result = wait_for_terminal_status(container_run_id)

    local_logs = get_json(f"/runs/{local_run_id}/logs")
    container_logs = get_json(f"/runs/{container_run_id}/logs")

    output = {
        "local": {
            "package_id": local_id,
            "run_id": local_run_id,
            "status": local_result.get("status") if local_result else None,
            "exit_code": local_result.get("exit_code") if local_result else None,
            "tail_logs": [x.get("line") for x in local_logs[-10:]],
        },
        "container": {
            "package_id": container_id,
            "run_id": container_run_id,
            "status": container_result.get("status") if container_result else None,
            "exit_code": container_result.get("exit_code") if container_result else None,
            "tail_logs": [x.get("line") for x in container_logs[-10:]],
        },
    }

    print(json.dumps(output, indent=2))

    if output["local"]["status"] != "completed":
        return 1
    if output["container"]["status"] != "completed":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
