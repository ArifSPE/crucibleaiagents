import json
import io
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from schemas.model import AgentPackage, RunEvents, RunLogs, Runs
from worker import worker as worker_module


def _make_test_package(tmp_path: Path) -> Path:
    pkg_root = tmp_path / "pkg"
    (pkg_root / "src").mkdir(parents=True)
    (pkg_root / "manifest.json").write_text(
        json.dumps({
            "name": "lifecycle-agent",
            "version": "1.0.0",
            "language": "python",
            "entrypoint": "src/agent.py",
        }),
        encoding="utf-8",
    )
    (pkg_root / "src" / "agent.py").write_text(
        "print('hello from worker')\n",
        encoding="utf-8",
    )
    return pkg_root


def test_worker_claim_and_execute_completes_run(client, db, monkeypatch, tmp_path):
    pkg_root = _make_test_package(tmp_path)

    package = AgentPackage(
        name="lifecycle-agent",
        version="1.0.0",
        language="python",
        storage_path=str(pkg_root),
        entry_point="src/agent.py",
        timeout_seconds=10,
        runtime_mode="batch",
    )
    db.add(package)
    db.commit()
    db.refresh(package)

    run = Runs(
        agent_package_id=package.id,
        status="pending",
        timeout_seconds=10,
        runtime_mode="batch",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    test_session_factory = sessionmaker(bind=db.bind, autocommit=False, autoflush=False)
    monkeypatch.setattr(worker_module, "SessionLocal", test_session_factory)

    claimed = worker_module._claim_next_run()
    assert claimed is not None
    assert claimed["id"] == run.id

    worker_module._execute_run(claimed)

    verify_db = test_session_factory()
    try:
        updated_run = verify_db.query(Runs).filter(Runs.id == run.id).first()
        assert updated_run is not None
        assert updated_run.status == "completed"
        assert updated_run.exit_code == 0
        assert updated_run.error is None

        logs = verify_db.query(RunLogs).filter(RunLogs.run_id == run.id).all()
        assert any("hello from worker" in log.line for log in logs)

        event_types = [
            event.type
            for event in verify_db.query(RunEvents).filter(RunEvents.run_id == run.id).all()
        ]
        assert "worker.run_start" in event_types
        assert "worker.run_complete" in event_types
    finally:
        verify_db.close()


def test_worker_container_deployment_uses_docker_runner(client, db, monkeypatch, tmp_path):
    pkg_root = tmp_path / "pkg_container"
    pkg_root.mkdir(parents=True)
    (pkg_root / "manifest.json").write_text(
        json.dumps({"name": "container-agent", "version": "1.0.0"}),
        encoding="utf-8",
    )

    package = AgentPackage(
        name="container-agent",
        version="1.0.0",
        language="python",
        storage_path=str(pkg_root),
        timeout_seconds=10,
        deployment="container",
    )
    db.add(package)
    db.commit()
    db.refresh(package)

    run = Runs(
        agent_package_id=package.id,
        status="pending",
        timeout_seconds=10,
        runtime_mode="batch",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    test_session_factory = sessionmaker(bind=db.bind, autocommit=False, autoflush=False)
    monkeypatch.setattr(worker_module, "SessionLocal", test_session_factory)
    monkeypatch.setenv("RUNNER_IMAGE", "test-runner:latest")

    captured = {"cmd": None}

    class _FakePopen:
        def __init__(self, cmd, **kwargs):
            captured["cmd"] = cmd
            self.stdout = io.StringIO("container log\n")
            self.stderr = io.StringIO("")

        def wait(self, timeout=None):
            return 0

        def kill(self):
            return None

    monkeypatch.setattr(worker_module.subprocess, "Popen", _FakePopen)

    claimed = worker_module._claim_next_run()
    assert claimed is not None
    worker_module._execute_run(claimed)

    verify_db = test_session_factory()
    try:
        updated_run = verify_db.query(Runs).filter(Runs.id == run.id).first()
        assert updated_run is not None
        assert updated_run.status == "completed"
        assert updated_run.exit_code == 0

        cmd = captured["cmd"]
        assert cmd is not None
        assert cmd[0:2] == ["docker", "run"]
        assert "test-runner:latest" in cmd
    finally:
        verify_db.close()


def test_local_worker_claims_only_local_deployment(client, db, monkeypatch):
    local_pkg = AgentPackage(name="local-claim-agent", version="1.0.0", language="python", deployment="local")
    container_pkg = AgentPackage(name="container-claim-agent", version="1.0.0", language="python", deployment="container")
    db.add(local_pkg)
    db.add(container_pkg)
    db.commit()
    db.refresh(local_pkg)
    db.refresh(container_pkg)

    local_run = Runs(agent_package_id=local_pkg.id, status="pending", timeout_seconds=10, runtime_mode="batch")
    container_run = Runs(agent_package_id=container_pkg.id, status="pending", timeout_seconds=10, runtime_mode="batch")
    db.add(local_run)
    db.add(container_run)
    db.commit()
    db.refresh(local_run)

    test_session_factory = sessionmaker(bind=db.bind, autocommit=False, autoflush=False)
    monkeypatch.setattr(worker_module, "SessionLocal", test_session_factory)

    claimed = worker_module._claim_next_run_for("local")
    assert claimed is not None
    assert claimed["id"] == local_run.id


def test_container_worker_claims_only_container_deployment(client, db, monkeypatch):
    local_pkg = AgentPackage(name="local-claim-agent-2", version="1.0.0", language="python", deployment="local")
    container_pkg = AgentPackage(name="container-claim-agent-2", version="1.0.0", language="python", deployment="container")
    db.add(local_pkg)
    db.add(container_pkg)
    db.commit()
    db.refresh(container_pkg)

    local_run = Runs(agent_package_id=local_pkg.id, status="pending", timeout_seconds=10, runtime_mode="batch")
    container_run = Runs(agent_package_id=container_pkg.id, status="pending", timeout_seconds=10, runtime_mode="batch")
    db.add(local_run)
    db.add(container_run)
    db.commit()
    db.refresh(container_run)

    test_session_factory = sessionmaker(bind=db.bind, autocommit=False, autoflush=False)
    monkeypatch.setattr(worker_module, "SessionLocal", test_session_factory)

    claimed = worker_module._claim_next_run_for("container")
    assert claimed is not None
    assert claimed["id"] == container_run.id


def test_local_execute_injects_run_context_env(client, db, monkeypatch, tmp_path):
    pkg_root = _make_test_package(tmp_path)

    package = AgentPackage(
        name="local-env-agent",
        version="1.0.0",
        language="python",
        storage_path=str(pkg_root),
        entry_point="src/agent.py",
        timeout_seconds=10,
        runtime_mode="batch",
        deployment="local",
    )
    db.add(package)
    db.commit()
    db.refresh(package)

    run = Runs(
        agent_package_id=package.id,
        status="pending",
        timeout_seconds=10,
        runtime_mode="batch",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    test_session_factory = sessionmaker(bind=db.bind, autocommit=False, autoflush=False)
    monkeypatch.setattr(worker_module, "SessionLocal", test_session_factory)
    monkeypatch.setenv("RUNNER_API_BASE_URL", "http://localhost:8080")

    captured = {"env": None}

    class _FakePopen:
        def __init__(self, cmd, **kwargs):
            captured["env"] = kwargs.get("env")
            self.stdout = io.StringIO("ok\n")
            self.stderr = io.StringIO("")

        def wait(self, timeout=None):
            return 0

        def kill(self):
            return None

    monkeypatch.setattr(worker_module.subprocess, "Popen", _FakePopen)

    claimed = worker_module._claim_next_run_for("local")
    assert claimed is not None
    worker_module._execute_run(claimed)

    assert captured["env"] is not None
    assert captured["env"]["RUN_ID"] == str(run.id)
    assert captured["env"]["API_BASE_URL"] == "http://localhost:8080"


def test_resolve_workspace_maps_workspace_prefix_to_repo_root(monkeypatch, tmp_path):
    mapped = tmp_path / "package" / "deployed" / "local-ts-sample-agent_pkg9"
    mapped.mkdir(parents=True)

    monkeypatch.setattr(worker_module, "REPO_ROOT", tmp_path)

    resolved = worker_module._resolve_workspace("/workspace/package/deployed/local-ts-sample-agent_pkg9")
    assert resolved == mapped


def test_enqueue_autostart_daemon_runs_for_container(client, db, monkeypatch):
    daemon_pkg = AgentPackage(
        name="daemon-autostart-container",
        version="1.0.0",
        language="python",
        deployment="container",
        runtime_mode="daemon",
        deamon_auto_restart=True,
        timeout_seconds=77,
    )
    db.add(daemon_pkg)
    db.commit()

    test_session_factory = sessionmaker(bind=db.bind, autocommit=False, autoflush=False)
    monkeypatch.setattr(worker_module, "SessionLocal", test_session_factory)

    created = worker_module._enqueue_autostart_daemon_runs("container")
    assert created == 1

    verify_db = test_session_factory()
    try:
        run = (
            verify_db.query(Runs)
            .filter(Runs.agent_package_id == daemon_pkg.id)
            .order_by(Runs.id.desc())
            .first()
        )
        assert run is not None
        assert run.runtime_mode == "daemon"
        assert run.status == "queued"
        assert run.timeout_seconds == 77
    finally:
        verify_db.close()

    # Idempotent: second enqueue should not create duplicates.
    created_again = worker_module._enqueue_autostart_daemon_runs("container")
    assert created_again == 0


def test_daemon_container_run_starts_detached_and_stays_running(client, db, monkeypatch, tmp_path):
    pkg_root = tmp_path / "daemon_pkg"
    pkg_root.mkdir(parents=True)
    (pkg_root / "manifest.json").write_text(
        json.dumps({"name": "daemon-run", "version": "1.0.0"}),
        encoding="utf-8",
    )

    pkg = AgentPackage(
        name="daemon-run",
        version="1.0.0",
        language="python",
        deployment="container",
        runtime_mode="daemon",
        deamon_auto_restart=True,
        storage_path=str(pkg_root),
        timeout_seconds=60,
        expoded_port=8099,
    )
    db.add(pkg)
    db.commit()
    db.refresh(pkg)

    run = Runs(
        agent_package_id=pkg.id,
        status="pending",
        timeout_seconds=60,
        runtime_mode="daemon",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    test_session_factory = sessionmaker(bind=db.bind, autocommit=False, autoflush=False)
    monkeypatch.setattr(worker_module, "SessionLocal", test_session_factory)

    captured = {"cmd": None}

    class _FakeRunResult:
        returncode = 0
        stdout = "daemon-container-id\n"
        stderr = ""

    def _fake_run(cmd, capture_output=True, text=True):
        captured["cmd"] = cmd
        return _FakeRunResult()

    monkeypatch.setattr(worker_module.subprocess, "run", _fake_run)

    claimed = worker_module._claim_next_run_for("container")
    assert claimed is not None
    worker_module._execute_run(claimed)

    verify_db = test_session_factory()
    try:
        updated = verify_db.query(Runs).filter(Runs.id == run.id).first()
        assert updated is not None
        assert updated.status == "running"
        assert updated.container_id == "daemon-container-id"
        assert updated.exposed_port == 8099

        event_types = [e.type for e in verify_db.query(RunEvents).filter(RunEvents.run_id == run.id).all()]
        assert "worker.daemon_started" in event_types
    finally:
        verify_db.close()

    cmd = captured["cmd"]
    assert cmd is not None
    assert cmd[0:3] == ["docker", "run", "-d"]
    assert "-p" in cmd
