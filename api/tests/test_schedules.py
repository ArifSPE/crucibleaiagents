"""
Tests for schedule CRUD endpoints:
  GET  /schedules
  GET  /schedules/{id}
  GET  /packages/{id}/schedules
  POST /packages/{id}/schedules
  PUT  /schedules/{id}
  PATCH /schedules/{id}/activate
  PATCH /schedules/{id}/deactivate
  DELETE /schedules/{id}
"""

_INTERVAL_PAYLOAD = {
    "schedule_type": "interval",
    "interval_seconds": 3600,
    "enabled": True,
}

_CRON_PAYLOAD = {
    "schedule_type": "cron",
    "cron_expression": "0 * * * *",
    "enabled": True,
}


# ── list all schedules ────────────────────────────────────────────────────────

def test_list_schedules_empty(client):
    resp = client.get("/schedules")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_schedules_returns_all(client, sample_package):
    client.post(f"/packages/{sample_package.id}/schedules", json=_INTERVAL_PAYLOAD)
    client.post(f"/packages/{sample_package.id}/schedules", json=_CRON_PAYLOAD)
    resp = client.get("/schedules")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


# ── get single schedule ───────────────────────────────────────────────────────

def test_get_schedule_found(client, sample_package):
    created = client.post(
        f"/packages/{sample_package.id}/schedules", json=_INTERVAL_PAYLOAD
    ).json()
    resp = client.get(f"/schedules/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_get_schedule_not_found(client):
    assert client.get("/schedules/99999").status_code == 404


def test_get_schedule_has_expected_fields(client, sample_package):
    created = client.post(
        f"/packages/{sample_package.id}/schedules", json=_INTERVAL_PAYLOAD
    ).json()
    body = client.get(f"/schedules/{created['id']}").json()
    for field in ("id", "package_id", "schedule_type", "schedule_config",
                  "is_active", "last_run_time", "next_run_time", "created_at"):
        assert field in body, f"Missing field: {field}"


# ── list schedules for package ────────────────────────────────────────────────

def test_list_schedules_for_package(client, sample_package):
    client.post(f"/packages/{sample_package.id}/schedules", json=_INTERVAL_PAYLOAD)
    client.post(f"/packages/{sample_package.id}/schedules", json=_CRON_PAYLOAD)
    resp = client.get(f"/packages/{sample_package.id}/schedules")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert all(s["package_id"] == sample_package.id for s in data)


def test_list_schedules_for_package_not_found(client):
    assert client.get("/packages/99999/schedules").status_code == 404


def test_list_schedules_for_package_empty(client, sample_package):
    resp = client.get(f"/packages/{sample_package.id}/schedules")
    assert resp.status_code == 200
    assert resp.json() == []


# ── create schedule ───────────────────────────────────────────────────────────

def test_create_schedule_interval(client, sample_package):
    resp = client.post(
        f"/packages/{sample_package.id}/schedules", json=_INTERVAL_PAYLOAD
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["schedule_type"] == "interval"
    assert body["package_id"] == sample_package.id
    assert body["is_active"] is True


def test_create_schedule_cron(client, sample_package):
    resp = client.post(
        f"/packages/{sample_package.id}/schedules", json=_CRON_PAYLOAD
    )
    assert resp.status_code == 201
    assert resp.json()["schedule_type"] == "cron"


def test_create_schedule_disabled(client, sample_package):
    payload = {**_INTERVAL_PAYLOAD, "enabled": False}
    resp = client.post(f"/packages/{sample_package.id}/schedules", json=payload)
    assert resp.status_code == 201
    assert resp.json()["is_active"] is False


def test_create_schedule_package_not_found(client):
    resp = client.post("/packages/99999/schedules", json=_INTERVAL_PAYLOAD)
    assert resp.status_code == 404


# ── update schedule ───────────────────────────────────────────────────────────

def test_update_schedule(client, sample_package):
    created = client.post(
        f"/packages/{sample_package.id}/schedules", json=_INTERVAL_PAYLOAD
    ).json()
    updated_payload = {**_INTERVAL_PAYLOAD, "interval_seconds": 7200}
    resp = client.put(f"/schedules/{created['id']}", json=updated_payload)
    assert resp.status_code == 200
    import json
    config = json.loads(resp.json()["schedule_config"])
    assert config["interval_seconds"] == 7200


def test_update_schedule_not_found(client):
    resp = client.put("/schedules/99999", json=_INTERVAL_PAYLOAD)
    assert resp.status_code == 404


def test_update_schedule_change_type(client, sample_package):
    created = client.post(
        f"/packages/{sample_package.id}/schedules", json=_INTERVAL_PAYLOAD
    ).json()
    resp = client.put(f"/schedules/{created['id']}", json=_CRON_PAYLOAD)
    assert resp.status_code == 200
    assert resp.json()["schedule_type"] == "cron"


# ── activate / deactivate ─────────────────────────────────────────────────────

def test_activate_schedule(client, sample_package):
    created = client.post(
        f"/packages/{sample_package.id}/schedules",
        json={**_INTERVAL_PAYLOAD, "enabled": False},
    ).json()

    resp = client.patch(f"/schedules/{created['id']}/activate")
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True


def test_activate_schedule_not_found(client):
    assert client.patch("/schedules/99999/activate").status_code == 404


def test_deactivate_schedule(client, sample_package):
    created = client.post(
        f"/packages/{sample_package.id}/schedules", json=_INTERVAL_PAYLOAD
    ).json()

    resp = client.patch(f"/schedules/{created['id']}/deactivate")
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


def test_deactivate_schedule_not_found(client):
    assert client.patch("/schedules/99999/deactivate").status_code == 404


# ── delete ────────────────────────────────────────────────────────────────────

def test_delete_schedule(client, sample_package):
    created = client.post(
        f"/packages/{sample_package.id}/schedules", json=_INTERVAL_PAYLOAD
    ).json()
    resp = client.delete(f"/schedules/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    # Confirm it's gone
    assert client.get(f"/schedules/{created['id']}").status_code == 404


def test_delete_schedule_not_found(client):
    assert client.delete("/schedules/99999").status_code == 404


def test_delete_schedule_removes_from_list(client, sample_package):
    created = client.post(
        f"/packages/{sample_package.id}/schedules", json=_INTERVAL_PAYLOAD
    ).json()
    schedule_id = created["id"]

    client.delete(f"/schedules/{schedule_id}")
    all_ids = [s["id"] for s in client.get("/schedules").json()]
    assert schedule_id not in all_ids
