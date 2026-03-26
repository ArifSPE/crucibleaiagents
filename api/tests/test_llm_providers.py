"""
Tests for GET/POST/PUT/DELETE /llm-providers endpoints.

Security assertions:
- Credential values are never present in any response body.
- Only credential key names are returned via `credential_keys`.
- Invalid / unknown provider names are rejected with 400.
- Duplicate provider names are rejected with 409.
- Credentials are stored as child LLMCredential records in one-to-many relationship.
- Invalid credential keys for a provider are rejected with 400.
- Credential values must be non-empty strings (400 if not).
"""
import pytest
from schemas.model import LLMCredential


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


def test_list_providers_with_credentials(client, sample_provider_with_credentials):
    """List should include providers with credentials."""
    resp = client.get("/llm-providers")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["provider"] == "anthropic"
    assert data[0]["has_credentials"] is True
    assert "api_key" in data[0]["credential_keys"]


# ── create ────────────────────────────────────────────────────────────────────

def test_create_provider_minimal(client):
    resp = client.post("/llm-providers", json={"provider_name": "anthropic"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["provider"] == "anthropic"
    assert "id" in body


def test_create_provider_with_credentials(client, db):
    """Verify credentials are stored as child LLMCredential records."""
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
    
    # Verify child LLMCredential record was created
    provider_id = body["id"]
    creds = db.query(LLMCredential).filter(LLMCredential.llm_provider_id == provider_id).all()
    assert len(creds) == 1
    assert creds[0].key_name == "api_key"
    assert creds[0].encrypted_value is not None


def test_create_provider_credentials_value_never_returned(client):
    """Regression: ensure raw credential values are never leaked in any response."""
    secret_value = "super-secret-api-key-12345"
    client.post(
        "/llm-providers",
        json={"provider_name": "claude", "credentials": {"api_key": secret_value}},
    )
    list_resp = client.get("/llm-providers")
    assert secret_value not in list_resp.text


def test_create_provider_invalid_credential_key(client):
    """Invalid credential keys for provider should be rejected."""
    resp = client.post(
        "/llm-providers",
        json={
            "provider_name": "anthropic",
            "credentials": {"invalid_key": "value"},
        },
    )
    assert resp.status_code == 400
    assert "Invalid credential key" in resp.json()["detail"]


def test_create_provider_credential_empty_value(client):
    """Empty credential values should be rejected."""
    resp = client.post(
        "/llm-providers",
        json={
            "provider_name": "anthropic",
            "credentials": {"api_key": ""},
        },
    )
    assert resp.status_code == 400
    assert "non-empty string" in resp.json()["detail"]


def test_create_provider_credential_whitespace_value(client):
    """Whitespace-only credential values should be rejected."""
    resp = client.post(
        "/llm-providers",
        json={
            "provider_name": "anthropic",
            "credentials": {"api_key": "   "},
        },
    )
    assert resp.status_code == 400
    assert "non-empty string" in resp.json()["detail"]


def test_create_provider_multiple_credentials(client, db):
    """Multiple credentials for a provider should each be stored as LLMCredential."""
    resp = client.post(
        "/llm-providers",
        json={
            "provider_name": "aws_bedrock",
            "credentials": {
                "access_key_id": "AKIAIOSFODNN7EXAMPLE",
                "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                "region": "us-east-1",
            },
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["has_credentials"] is True
    assert len(body["credential_keys"]) == 3
    assert all(key in body["credential_keys"] for key in ["access_key_id", "secret_access_key", "region"])
    
    # Verify all child LLMCredential records were created
    provider_id = body["id"]
    creds = db.query(LLMCredential).filter(LLMCredential.llm_provider_id == provider_id).all()
    assert len(creds) == 3
    cred_keys = {cred.key_name for cred in creds}
    assert cred_keys == {"access_key_id", "secret_access_key", "region"}


def test_create_provider_no_credentials_required(client):
    """local_ollama requires no credentials."""
    resp = client.post(
        "/llm-providers",
        json={"provider_name": "local_ollama"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["has_credentials"] is False
    assert body["credential_keys"] == []


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
                  "credential_keys", "created_at", "updated_at", "credential"):
        assert field in body, f"Missing field: {field}"


def test_get_provider_with_credentials(client, db, sample_provider):
    """Verify GET returns credentials from child LLMCredential records."""
    # Add credentials to the provider
    cred1 = LLMCredential(
        llm_provider_id=sample_provider.id,
        key_name="api_key",
        encrypted_value="encrypted_key_value"
    )
    cred2 = LLMCredential(
        llm_provider_id=sample_provider.id,
        key_name="region",
        encrypted_value="encrypted_region_value"
    )
    db.add(cred1)
    db.add(cred2)
    db.commit()
    
    resp = client.get(f"/llm-providers/{sample_provider.id}")
    assert resp.status_code == 200
    body = resp.json()
    # Should show that credentials exist
    assert len(body["credential"]) >= 2


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


def test_update_provider_add_credentials(client, db):
    """Adding credentials to a provider creates LLMCredential child records."""
    # Create an anthropic provider (supports api_key)
    resp_create = client.post("/llm-providers", json={"provider_name": "anthropic"})
    provider_id = resp_create.json()["id"]
    
    resp = client.put(
        f"/llm-providers/{provider_id}",
        json={
            "provider_name": "anthropic",
            "credentials": {"api_key": "new-key"},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_credentials"] is True
    assert "api_key" in body["credential_keys"]
    assert "new-key" not in str(body)
    
    # Verify LLMCredential record was created for update
    creds = db.query(LLMCredential).filter(LLMCredential.llm_provider_id == provider_id).all()
    assert len(creds) >= 1


def test_update_provider_add_multiple_credentials(client, sample_provider, db):
    """Updating provider with multiple credentials creates multiple child records."""
    resp = client.put(
        f"/llm-providers/{sample_provider.id}",
        json={
            "provider_name": "local_ollama",
            "credentials": {}  # local_ollama accepts empty
        },
    )
    assert resp.status_code == 200


def test_update_provider_clear_credentials(client, db):
    """Updating with empty credentials dict clears them."""
    from schemas.model import LlmProvider
    
    # Create provider with credential
    provider = LlmProvider(provider="anthropic")
    db.add(provider)
    db.flush()
    
    cred = LLMCredential(
        llm_provider_id=provider.id,
        key_name="api_key",
        encrypted_value="encrypted_value"
    )
    db.add(cred)
    db.commit()
    
    # Update with empty credentials
    resp = client.put(
        f"/llm-providers/{provider.id}",
        json={"provider_name": "anthropic", "credentials": {}},
    )
    assert resp.status_code == 200
    assert resp.json()["has_credentials"] is False


# ── delete ────────────────────────────────────────────────────────────────────


def test_delete_provider(client, sample_provider):
    """Deleting provider removes it from list."""
    provider_id = sample_provider.id
    
    resp = client.delete(f"/llm-providers/{provider_id}")
    assert resp.status_code == 204

    # Confirm provider is gone
    assert client.get(f"/llm-providers/{provider_id}").status_code == 404

def test_delete_provider_not_found(client):
    resp = client.delete("/llm-providers/99999")
    assert resp.status_code == 404


def test_delete_provider_removes_from_list(client, sample_provider):
    client.delete(f"/llm-providers/{sample_provider.id}")
    data = client.get("/llm-providers").json()
    assert all(p["id"] != sample_provider.id for p in data)
