"""
Tests for run endpoints:
  GET  /runs
  POST /runs?package_id={id}
  GET  /runs/{id}
  GET  /runs/{id}/logs
  GET  /runs/{id}/events
  GET  /runs/package/{package_id}
"""


# ── list all runs ─────────────────────────────────────────────────────────────

def test_list_runs_empty(client):
    resp = client.get("/runs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_runs_returns_all(client, sample_package):
    client.post(f"/runs?package_id={sample_package.id}")
    client.post(f"/runs?package_id={sample_package.id}")
    data = client.get("/runs").json()
    assert len(data) == 2


def test_list_runs_has_expected_fields(client, sample_run):
    data = client.get("/runs").json()
    assert len(data) == 1
    body = data[0]
    for field in (
        "id", "agent_package_id", "status", "runtime_mode",
        "started_at", "completed_at", "stopped_at",
        "timeout_seconds", "exit_code", "error",
        "container_id", "last_health_check", "restart_count", "exposed_port",
    ):
        assert field in body, f"Missing field: {field}"


# ── create run ────────────────────────────────────────────────────────────────

def test_create_run(client, sample_package):
    resp = client.post(f"/runs?package_id={sample_package.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["agent_package_id"] == sample_package.id
    assert body["status"] == "pending"


def test_create_run_package_not_found(client):
    resp = client.post("/runs?package_id=99999")
    assert resp.status_code == 404


def test_create_run_inherits_package_timeout(client, sample_package):
    resp = client.post(f"/runs?package_id={sample_package.id}")
    assert resp.json()["timeout_seconds"] == sample_package.timeout_seconds


# ── get single run ────────────────────────────────────────────────────────────

def test_get_run_found(client, sample_run):
    resp = client.get(f"/runs/{sample_run.id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == sample_run.id


def test_get_run_not_found(client):
    assert client.get("/runs/99999").status_code == 404


def test_get_run_has_expected_fields(client, sample_run):
    body = client.get(f"/runs/{sample_run.id}").json()
    for field in (
        "id", "agent_package_id", "status", "runtime_mode",
        "started_at", "completed_at", "stopped_at",
        "timeout_seconds", "exit_code", "error",
        "container_id", "exposed_port", "restart_count", "last_health_check",
    ):
        assert field in body, f"Missing field: {field}"


# ── run logs ──────────────────────────────────────────────────────────────────

def test_get_run_logs_empty(client, sample_run):
    resp = client.get(f"/runs/{sample_run.id}/logs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_run_logs_run_not_found(client):
    assert client.get("/runs/99999/logs").status_code == 404


def test_get_run_logs_returns_seeded_log(client, db, sample_run):
    from schemas.model import RunLogs
    log = RunLogs(
        run_id=sample_run.id,
        stream="stdout",
        level="INFO",
        line="Hello from the agent",
    )
    db.add(log)
    db.commit()

    data = client.get(f"/runs/{sample_run.id}/logs").json()
    assert len(data) == 1
    assert data[0]["line"] == "Hello from the agent"
    assert data[0]["stream"] == "stdout"


def test_get_run_logs_has_expected_fields(client, db, sample_run):
    from schemas.model import RunLogs
    db.add(RunLogs(run_id=sample_run.id, stream="stderr", level="ERROR", line="oops"))
    db.commit()

    log = client.get(f"/runs/{sample_run.id}/logs").json()[0]
    for field in ("id", "run_id", "ts", "stream", "level", "line", "section"):
        assert field in log, f"Missing log field: {field}"


# ── run events ────────────────────────────────────────────────────────────────

def test_get_run_events_empty(client, sample_run):
    resp = client.get(f"/runs/{sample_run.id}/events")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_run_events_run_not_found(client):
    assert client.get("/runs/99999/events").status_code == 404


def test_get_run_events_returns_seeded_event(client, db, sample_run):
    from schemas.model import RunEvents
    event = RunEvents(
        run_id=sample_run.id,
        type="runner_boot",
        level="INFO",
        category="infrastructure",
        source="runner",
        message="Runner started",
        payload_jason="{}",
    )
    db.add(event)
    db.commit()

    data = client.get(f"/runs/{sample_run.id}/events").json()
    assert len(data) == 1
    assert data[0]["type"] == "runner_boot"
    assert data[0]["message"] == "Runner started"


def test_get_run_events_has_expected_fields(client, db, sample_run):
    from schemas.model import RunEvents
    db.add(RunEvents(
        run_id=sample_run.id, type="step_start", level="INFO",
        category="agent", source="agent", payload_jason="{}",
    ))
    db.commit()

    event = client.get(f"/runs/{sample_run.id}/events").json()[0]
    for field in ("id", "run_id", "ts", "type", "level", "category", "source",
                  "message", "payload_jason"):
        assert field in event, f"Missing event field: {field}"


def test_post_run_event_creates_event(client, sample_run):
    resp = client.post(
        f"/runs/{sample_run.id}/events",
        json={"type": "step_start", "payload": {"name": "prepare"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == sample_run.id
    assert body["type"] == "step_start"
    assert body["payload_jason"] == '{"name": "prepare"}'


def test_post_run_log_creates_log(client, sample_run):
    resp = client.post(
        f"/runs/{sample_run.id}/logs",
        json={"stream": "stdout", "level": "INFO", "line": "agent says hello", "section": "agent"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == sample_run.id
    assert body["line"] == "agent says hello"
    assert body["stream"] == "stdout"


# ── runs by package ───────────────────────────────────────────────────────────

def test_get_runs_by_package_empty(client, sample_package):
    resp = client.get(f"/runs/package/{sample_package.id}")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_runs_by_package_returns_correct_runs(client, db, sample_package):
    from schemas.model import AgentPackage, Runs
    # Second package
    other = AgentPackage(name="other-pkg", version="0.1")
    db.add(other)
    db.commit()
    db.refresh(other)

    # One run for sample_package, one for other
    db.add(Runs(agent_package_id=sample_package.id, status="pending"))
    db.add(Runs(agent_package_id=other.id, status="running"))
    db.commit()

    data = client.get(f"/runs/package/{sample_package.id}").json()
    assert len(data) == 1
    assert data[0]["agent_package_id"] == sample_package.id


def test_get_runs_by_package_ordered_newest_first(client, sample_package):
    client.post(f"/runs?package_id={sample_package.id}")
    client.post(f"/runs?package_id={sample_package.id}")
    data = client.get(f"/runs/package/{sample_package.id}").json()
    assert len(data) == 2
    assert data[0]["id"] > data[1]["id"]
