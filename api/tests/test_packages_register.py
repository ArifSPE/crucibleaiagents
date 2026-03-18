"""Tests for metadata-only package registration endpoint."""

import os


def test_register_package_persists_schedule_and_manifest_metadata(client, db):
    payload = {
        "name": "meta-rich-agent",
        "version": "1.0.0",
        "language": "python",
        "entrypoint": "src/agent.py",
        "schedule_enabled": True,
        "schedule_type": "cron",
        "schedule_config": {"cron_expr": "*/15 * * * *"},
        "secret_keys": ["API_KEY", "TENANT_ID"],
        "environment": {"API_KEY": "{secrets.API_KEY}", "LOG_LEVEL": "INFO"},
        "llm_provider": {"use_platform": True, "provider_id": 4},
        "tool_bindings": [{"tool_key": "shell.command", "config": {"default_command": "date"}}],
        "manifest_metadata": {"tags": ["demo", "ops"]},
    }

    resp = client.post("/packages/register", json=payload)
    assert resp.status_code == 200
    package_id = resp.json()["id"]

    from schemas.model import AgentPackage, PackageSecret, PackageSchedule

    package = db.query(AgentPackage).filter(AgentPackage.id == package_id).first()
    assert package is not None
    assert package.schedule_enables is False
    assert package.schedule_type == "cron"
    assert package.schedule_congig == {"cron_expr": "*/15 * * * *"}
    assert package.description_json["secret_keys"] == ["API_KEY", "TENANT_ID"]
    assert package.description_json["manifest_metadata"]["tags"] == ["demo", "ops"]

    provisioned_secret_keys = sorted(
        s.key_name for s in db.query(PackageSecret).filter(PackageSecret.package_id == package_id).all()
    )
    assert provisioned_secret_keys == ["API_KEY", "TENANT_ID"]

    schedule_row = db.query(PackageSchedule).filter(PackageSchedule.package_id == package_id).first()
    assert schedule_row is not None
    assert schedule_row.schedule_type == "cron"
    assert schedule_row.is_active is False

    fetched = client.get(f"/packages/{package_id}")
    assert fetched.status_code == 200
    fetched_body = fetched.json()
    assert fetched_body["schedule_config"] == {"cron_expr": "*/15 * * * *"}
    assert fetched_body["secret_keys"] == ["API_KEY", "TENANT_ID"]
    assert fetched_body["schedule_requested_enabled"] is True
    assert fetched_body["schedule_activation_blocked"] is True
    assert fetched_body["missing_secret_keys"] == ["API_KEY", "TENANT_ID"]


def test_register_package_action_new_rejects_existing_name(client, sample_package):
    payload = {
        "name": sample_package.name,
        "version": "1.0.1",
        "manifest_metadata": {"normalized_action": "new"},
    }
    resp = client.post("/packages/register", json=payload)
    assert resp.status_code == 400


def test_register_package_action_update_requires_existing(client):
    payload = {
        "name": "missing-agent",
        "version": "1.0.1",
        "manifest_metadata": {"normalized_action": "update"},
    }
    resp = client.post("/packages/register", json=payload)
    assert resp.status_code == 404


def test_register_package_creates_metadata(client):
    payload = {
        "name": "watcher-agent",
        "version": "1.2.3",
        "description": "Watcher registered package",
        "language": "python",
        "entrypoint": "main.py",
        "timeout_seconds": 120,
        "filename": "watcher-agent.zip",
        "runtime_mode": "batch",
        "deployment": "container",
        "restart_policy": "on-failure",
        "daemon_auto_start": False,
        "exposed_port": 8080,
    }

    resp = client.post("/packages/register", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] is True
    assert body["name"] == "watcher-agent"
    assert body["version"] == "1.2.3"

    fetched = client.get(f"/packages/{body['id']}")
    assert fetched.status_code == 200
    fetched_body = fetched.json()
    assert fetched_body["name"] == "watcher-agent"
    assert fetched_body["entrypoint"] == "main.py"
    assert fetched_body["timeout_seconds"] == 120
    assert fetched_body["deployment"] == "container"
    assert fetched_body["exposed_port"] == 8080


def test_register_package_updates_existing(client, sample_package):
    payload = {
        "name": sample_package.name,
        "version": "9.9.9",
        "description": "Updated by watcher",
        "language": "py",
        "entrypoint": "runner.py",
        "timeout_seconds": 300,
        "filename": "updated.zip",
    }

    resp = client.post("/packages/register", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] is False
    assert body["id"] == sample_package.id
    assert body["version"] == "9.9.9"

    fetched = client.get(f"/packages/{sample_package.id}")
    assert fetched.status_code == 200
    fetched_body = fetched.json()
    assert fetched_body["version"] == "9.9.9"
    assert fetched_body["entrypoint"] == "runner.py"
    assert fetched_body["timeout_seconds"] == 300


def test_register_package_rejects_empty_name(client):
    resp = client.post("/packages/register", json={"name": "   ", "version": "1.0.0"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Package name is required"


def test_register_package_defaults_deployment_to_local(client):
    resp = client.post(
        "/packages/register",
        json={
            "name": "local-default-agent",
            "version": "1.0.0",
            "language": "python",
        },
    )
    assert resp.status_code == 200
    package_id = resp.json()["id"]

    fetched = client.get(f"/packages/{package_id}")
    assert fetched.status_code == 200
    assert fetched.json()["deployment"] == "local"


def test_register_package_sets_deterministic_storage_path(client, db):
    resp = client.post(
        "/packages/register",
        json={
            "name": "storage-path-agent",
            "version": "1.0.0",
            "language": "python",
            "entrypoint": "src/agent.py",
        },
    )
    assert resp.status_code == 200
    package_id = resp.json()["id"]

    from schemas.model import AgentPackage

    pkg = db.query(AgentPackage).filter(AgentPackage.id == package_id).first()
    assert pkg is not None
    assert pkg.storage_path is not None
    assert pkg.storage_path == os.path.join(
        os.environ["STORAGE_DIR"],
        f"storage-path-agent_pkg{package_id}",
    )
