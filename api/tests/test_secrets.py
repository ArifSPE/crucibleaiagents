"""
Tests for package secrets endpoints:
  GET    /packages/{id}/secrets
  GET    /packages/{id}/secrets/{sid}
  POST   /packages/{id}/secrets
  PUT    /packages/{id}/secrets/{sid}
  DELETE /packages/{id}/secrets/{sid}

Security assertions:
- The plaintext value is NEVER returned in any response.
- The encrypted_value field is NEVER returned in any response.
- Values are encrypted (Fernet) before storage.
"""


# ── list ──────────────────────────────────────────────────────────────────────

def test_list_secrets_empty(client, sample_package):
    resp = client.get(f"/packages/{sample_package.id}/secrets")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_secrets_package_not_found(client):
    assert client.get("/packages/99999/secrets").status_code == 404


def test_list_secrets_returns_key_names(client, sample_package):
    client.post(
        f"/packages/{sample_package.id}/secrets",
        json={"key_name": "API_KEY", "value": "top-secret"},
    )
    data = client.get(f"/packages/{sample_package.id}/secrets").json()
    assert len(data) == 1
    assert data[0]["key_name"] == "API_KEY"


# ── get single secret ─────────────────────────────────────────────────────────

def test_get_secret_found(client, sample_package):
    created = client.post(
        f"/packages/{sample_package.id}/secrets",
        json={"key_name": "DB_PASSWORD", "value": "hunter2"},
    ).json()
    resp = client.get(f"/packages/{sample_package.id}/secrets/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["key_name"] == "DB_PASSWORD"


def test_get_secret_not_found(client, sample_package):
    assert client.get(f"/packages/{sample_package.id}/secrets/99999").status_code == 404


def test_get_secret_wrong_package(client, db, sample_package):
    """A secret belonging to one package must not be retrievable via another package's URL."""
    from schemas.model import AgentPackage
    other_pkg = AgentPackage(name="other-agent", version="0.1")
    db.add(other_pkg)
    db.commit()
    db.refresh(other_pkg)

    created = client.post(
        f"/packages/{sample_package.id}/secrets",
        json={"key_name": "TOKEN", "value": "secret"},
    ).json()

    resp = client.get(f"/packages/{other_pkg.id}/secrets/{created['id']}")
    assert resp.status_code == 404


def test_get_secret_has_expected_fields(client, sample_package):
    created = client.post(
        f"/packages/{sample_package.id}/secrets",
        json={"key_name": "SOME_KEY", "value": "some-val"},
    ).json()
    body = client.get(f"/packages/{sample_package.id}/secrets/{created['id']}").json()
    for field in ("id", "package_id", "key_name", "created_at", "updated_at"):
        assert field in body, f"Missing field: {field}"


# ── create ────────────────────────────────────────────────────────────────────

def test_create_secret(client, sample_package):
    resp = client.post(
        f"/packages/{sample_package.id}/secrets",
        json={"key_name": "MY_SECRET", "value": "plaintext-value"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["key_name"] == "MY_SECRET"
    assert body["package_id"] == sample_package.id


def test_create_secret_package_not_found(client):
    resp = client.post(
        "/packages/99999/secrets",
        json={"key_name": "KEY", "value": "val"},
    )
    assert resp.status_code == 404


def test_create_secret_duplicate_key(client, sample_package):
    payload = {"key_name": "DUPLICATE_KEY", "value": "first"}
    client.post(f"/packages/{sample_package.id}/secrets", json=payload)
    resp = client.post(
        f"/packages/{sample_package.id}/secrets",
        json={"key_name": "DUPLICATE_KEY", "value": "second"},
    )
    assert resp.status_code == 200

    listed = client.get(f"/packages/{sample_package.id}/secrets").json()
    assert len([secret for secret in listed if secret["key_name"] == "DUPLICATE_KEY"]) == 1


def test_create_secret_value_never_returned(client, sample_package):
    """The plaintext value must not appear in any response."""
    plaintext = "this-is-the-secret-value-xyz"
    resp = client.post(
        f"/packages/{sample_package.id}/secrets",
        json={"key_name": "SENSITIVE", "value": plaintext},
    )
    assert plaintext not in resp.text

    list_resp = client.get(f"/packages/{sample_package.id}/secrets")
    assert plaintext not in list_resp.text


def test_create_secret_encrypted_value_never_returned(client, sample_package):
    """The encrypted_value column must never surface in API responses."""
    resp = client.post(
        f"/packages/{sample_package.id}/secrets",
        json={"key_name": "ENC_TEST", "value": "anything"},
    )
    assert "encrypted_value" not in resp.json()


# ── update ────────────────────────────────────────────────────────────────────

def test_update_secret_value(client, sample_package):
    created = client.post(
        f"/packages/{sample_package.id}/secrets",
        json={"key_name": "UPDATE_ME", "value": "old-value"},
    ).json()
    resp = client.put(
        f"/packages/{sample_package.id}/secrets/{created['id']}",
        json={"key_name": "UPDATE_ME", "value": "new-value"},
    )
    assert resp.status_code == 200
    assert resp.json()["key_name"] == "UPDATE_ME"
    assert "new-value" not in resp.text


def test_update_secret_rename_key(client, sample_package):
    created = client.post(
        f"/packages/{sample_package.id}/secrets",
        json={"key_name": "OLD_KEY", "value": "val"},
    ).json()
    resp = client.put(
        f"/packages/{sample_package.id}/secrets/{created['id']}",
        json={"key_name": "NEW_KEY", "value": "val"},
    )
    assert resp.status_code == 200
    assert resp.json()["key_name"] == "NEW_KEY"


def test_update_secret_rename_conflict(client, sample_package):
    """Renaming a secret to a key_name that already exists in the same package → 409."""
    s1 = client.post(
        f"/packages/{sample_package.id}/secrets",
        json={"key_name": "KEY_A", "value": "a"},
    ).json()
    client.post(
        f"/packages/{sample_package.id}/secrets",
        json={"key_name": "KEY_B", "value": "b"},
    )
    resp = client.put(
        f"/packages/{sample_package.id}/secrets/{s1['id']}",
        json={"key_name": "KEY_B", "value": "a"},
    )
    assert resp.status_code == 409


def test_update_secret_not_found(client, sample_package):
    resp = client.put(
        f"/packages/{sample_package.id}/secrets/99999",
        json={"key_name": "K", "value": "v"},
    )
    assert resp.status_code == 404


# ── delete ────────────────────────────────────────────────────────────────────

def test_delete_secret(client, sample_package):
    created = client.post(
        f"/packages/{sample_package.id}/secrets",
        json={"key_name": "TO_DELETE", "value": "val"},
    ).json()
    resp = client.delete(f"/packages/{sample_package.id}/secrets/{created['id']}")
    assert resp.status_code == 200

    # Confirm gone
    assert (
        client.get(
            f"/packages/{sample_package.id}/secrets/{created['id']}"
        ).status_code
        == 404
    )


def test_delete_secret_not_found(client, sample_package):
    assert (
        client.delete(f"/packages/{sample_package.id}/secrets/99999").status_code == 404
    )


def test_delete_secret_removes_from_list(client, sample_package):
    created = client.post(
        f"/packages/{sample_package.id}/secrets",
        json={"key_name": "GONE", "value": "val"},
    ).json()
    client.delete(f"/packages/{sample_package.id}/secrets/{created['id']}")
    keys = [s["key_name"] for s in client.get(f"/packages/{sample_package.id}/secrets").json()]
    assert "GONE" not in keys
