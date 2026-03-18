"""
Tests for GET/POST/PUT/DELETE /llm-providers endpoints.

Security assertions:
- Credential values are never present in any response body.
- Only credential key names are returned via `credential_keys`.
- Invalid / unknown provider names are rejected with 400.
- Duplicate provider names are rejected with 409.
"""
import pytest


# ── list ──────────────────────────────────────────────────────────────────────

def test_list_providers_empty(client):
    resp = client.get("/llm-providers")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_providers_returns_all(client, sample_provider):
    resp = client.get("/llm-providers")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["provider"] == "local_ollama"


# ── create ────────────────────────────────────────────────────────────────────

def test_create_provider_minimal(client):
    resp = client.post("/llm-providers", json={"provider_name": "anthropic"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["provider"] == "anthropic"
    assert "id" in body


def test_create_provider_with_credentials(client):
    resp = client.post(
        "/llm-providers",
        json={
            "provider_name": "anthropic",
            "description": "Anthropic Claude",
            "credentials": {"api_key": "sk-secret-key"},
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["has_credentials"] is True
    assert "api_key" in body["credential_keys"]
    # Value must never appear in the response
    assert "sk-secret-key" not in str(body)


def test_create_provider_credentials_value_never_returned(client):
    """Regression: ensure raw credential values are never leaked in any response."""
    secret_value = "super-secret-api-key-12345"
    client.post(
        "/llm-providers",
        json={"provider_name": "claude", "credentials": {"api_key": secret_value}},
    )
    list_resp = client.get("/llm-providers")
    assert secret_value not in list_resp.text


def test_create_provider_invalid_name(client):
    resp = client.post("/llm-providers", json={"provider_name": "unknown_provider_xyz"})
    assert resp.status_code == 400


def test_create_provider_duplicate(client, sample_provider):
    resp = client.post("/llm-providers", json={"provider_name": "local_ollama"})
    assert resp.status_code == 409


def test_create_provider_with_endpoint(client):
    resp = client.post(
        "/llm-providers",
        json={
            "provider_name": "local_ollama",
            "endpoint": "http://localhost:11434",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["endpoint"] == "http://localhost:11434"


# ── get ───────────────────────────────────────────────────────────────────────

def test_get_provider_found(client, sample_provider):
    resp = client.get(f"/llm-providers/{sample_provider.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == sample_provider.id
    assert body["provider"] == "local_ollama"


def test_get_provider_not_found(client):
    resp = client.get("/llm-providers/99999")
    assert resp.status_code == 404


def test_get_provider_has_expected_fields(client, sample_provider):
    body = client.get(f"/llm-providers/{sample_provider.id}").json()
    for field in ("id", "provider", "description", "endpoint", "has_credentials",
                  "credential_keys", "created_at", "updated_at"):
        assert field in body, f"Missing field: {field}"


# ── update ────────────────────────────────────────────────────────────────────

def test_update_provider(client, sample_provider):
    resp = client.put(
        f"/llm-providers/{sample_provider.id}",
        json={"provider_name": "local_ollama", "description": "Updated description"},
    )
    assert resp.status_code == 200
    assert resp.json()["description"] == "Updated description"


def test_update_provider_not_found(client):
    resp = client.put("/llm-providers/99999", json={"provider_name": "anthropic"})
    assert resp.status_code == 404


def test_update_provider_rename_conflict(client, db):
    from schemas.model import LlmProvider
    p2 = LlmProvider(provider="anthropic")
    db.add(p2)
    db.commit()
    db.refresh(p2)

    # Create a second provider to rename conflictingly
    resp_create = client.post("/llm-providers", json={"provider_name": "local_ollama"})
    created_id = resp_create.json()["id"]

    # Try to rename it to "anthropic" which already exists
    resp = client.put(
        f"/llm-providers/{created_id}",
        json={"provider_name": "anthropic"},
    )
    assert resp.status_code == 409


def test_update_provider_add_credentials(client, sample_provider):
    resp = client.put(
        f"/llm-providers/{sample_provider.id}",
        json={
            "provider_name": "local_ollama",
            "credentials": {"api_key": "new-key"},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_credentials"] is True
    assert "api_key" in body["credential_keys"]
    assert "new-key" not in str(body)


def test_update_provider_clear_credentials(client, db):
    from schemas.model import LlmProvider
    import json
    from cryptography.fernet import Fernet
    import os
    import base64

    # Directly seed a provider with credentials to avoid routing through POST
    key = os.environ["SECRETS_ENCRYPTION_KEY"]
    fernet = Fernet(key.encode())
    encrypted = base64.b64encode(fernet.encrypt(json.dumps({"api_key": "x"}).encode())).decode()
    p = LlmProvider(provider="anthropic", encrypted_credentials=encrypted)
    db.add(p)
    db.commit()
    db.refresh(p)

    # Update with empty credentials dict to clear them
    resp = client.put(
        f"/llm-providers/{p.id}",
        json={"provider_name": "anthropic", "credentials": {}},
    )
    assert resp.status_code == 200
    assert resp.json()["has_credentials"] is False


# ── delete ────────────────────────────────────────────────────────────────────

def test_delete_provider(client, sample_provider):
    resp = client.delete(f"/llm-providers/{sample_provider.id}")
    assert resp.status_code == 204

    # Confirm it's gone
    assert client.get(f"/llm-providers/{sample_provider.id}").status_code == 404


def test_delete_provider_not_found(client):
    resp = client.delete("/llm-providers/99999")
    assert resp.status_code == 404


def test_delete_provider_removes_from_list(client, sample_provider):
    client.delete(f"/llm-providers/{sample_provider.id}")
    data = client.get("/llm-providers").json()
    assert all(p["id"] != sample_provider.id for p in data)
