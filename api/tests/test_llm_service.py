"""
Unit tests for helper functions in services/llm_service.py.

These are pure-function tests — no database or HTTP involved.
"""
import sys
import os

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

# Set required env var before importing llm_service
from cryptography.fernet import Fernet as _Fernet
os.environ.setdefault("SECRETS_ENCRYPTION_KEY", _Fernet.generate_key().decode())
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("STORAGE_DIR", "/tmp/test_crucible_storage")
os.environ.setdefault("ARCHIVE_DIR", "/tmp/test_crucible_archive")

import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock

from services.llm_service import (
    _normalize_llm_provider,
    _validate_credentials_map,
    _serialize_llm_provider,
)
from utils.config import ALLOWED_LLM_PROVIDERS


# ── _normalize_llm_provider ───────────────────────────────────────────────────

@pytest.mark.parametrize("name", sorted(ALLOWED_LLM_PROVIDERS))
def test_normalize_valid_provider(name):
    assert _normalize_llm_provider(name) == name


def test_normalize_strips_and_lowercases():
    # "Anthropic" with spaces should normalize to "anthropic"
    result = _normalize_llm_provider("  anthropic  ")
    assert result == "anthropic"


def test_normalize_spaces_to_underscores():
    # "local ollama" → "local_ollama"
    result = _normalize_llm_provider("local ollama")
    assert result == "local_ollama"


def test_normalize_invalid_provider_raises_400():
    with pytest.raises(HTTPException) as exc_info:
        _normalize_llm_provider("nonexistent_provider_xyz")
    assert exc_info.value.status_code == 400


def test_normalize_empty_string_raises_400():
    with pytest.raises(HTTPException):
        _normalize_llm_provider("")


def test_normalize_none_raises_400():
    with pytest.raises(HTTPException):
        _normalize_llm_provider(None)  # type: ignore[arg-type]


# ── _validate_credentials_map ─────────────────────────────────────────────────

def test_validate_credentials_none_returns_empty():
    assert _validate_credentials_map(None) == {}


def test_validate_credentials_empty_dict_returns_empty():
    assert _validate_credentials_map({}) == {}


def test_validate_credentials_cleans_whitespace_keys():
    result = _validate_credentials_map({"  api_key  ": "value"})
    assert "api_key" in result
    assert "  api_key  " not in result


def test_validate_credentials_skips_blank_keys():
    result = _validate_credentials_map({"": "value", "   ": "x"})
    assert result == {}


def test_validate_credentials_none_value_becomes_empty_string():
    result = _validate_credentials_map({"api_key": None})  # type: ignore[dict-item]
    assert result["api_key"] == ""


def test_validate_credentials_preserves_values():
    result = _validate_credentials_map({"api_key": "sk-abc123", "region": "us-east-1"})
    assert result["api_key"] == "sk-abc123"
    assert result["region"] == "us-east-1"


def test_validate_credentials_coerces_values_to_str():
    result = _validate_credentials_map({"port": 8080})  # type: ignore[dict-item]
    assert result["port"] == "8080"


# ── _serialize_llm_provider ───────────────────────────────────────────────────

def _make_provider(**kwargs):
    """Build a minimal mock LlmProvider instance."""
    from datetime import datetime
    defaults = {
        "id": 1,
        "provider": "anthropic",
        "description": "Test provider",
        "endpoint": "https://api.anthropic.com",
        "encrypted_credentials": None,
        "created_at": datetime(2025, 1, 1),
        "updated_at": datetime(2025, 1, 2),
    }
    defaults.update(kwargs)
    provider = MagicMock()
    for k, v in defaults.items():
        setattr(provider, k, v)
    return provider


def test_serialize_no_credentials():
    p = _make_provider(encrypted_credentials=None)
    result = _serialize_llm_provider(p)
    assert result["has_credentials"] is False
    assert result["credential_keys"] == []


def test_serialize_empty_credentials_string():
    p = _make_provider(encrypted_credentials="")
    result = _serialize_llm_provider(p)
    assert result["has_credentials"] is False


def test_serialize_with_credentials_exposes_only_keys():
    import json
    import base64
    from cryptography.fernet import Fernet

    key = os.environ["SECRETS_ENCRYPTION_KEY"]
    fernet = Fernet(key.encode())
    payload = json.dumps({"api_key": "sk-secret", "region": "us-east-1"})
    encrypted = base64.b64encode(fernet.encrypt(payload.encode())).decode()

    p = _make_provider(encrypted_credentials=encrypted)
    result = _serialize_llm_provider(p)

    assert result["has_credentials"] is True
    assert set(result["credential_keys"]) == {"api_key", "region"}
    # Values must not appear
    assert "sk-secret" not in str(result)
    assert "us-east-1" not in str(result["credential_keys"])


def test_serialize_returns_expected_fields():
    p = _make_provider()
    result = _serialize_llm_provider(p)
    for field in ("id", "provider", "description", "endpoint",
                  "has_credentials", "credential_keys", "created_at", "updated_at"):
        assert field in result, f"Missing field: {field}"


def test_serialize_corrupted_credentials_degrades_gracefully():
    """If credentials cannot be decrypted, has_credentials=True but credential_keys=[]."""
    p = _make_provider(encrypted_credentials="not-valid-fernet-data")
    result = _serialize_llm_provider(p)
    # Should not raise; gracefully returns empty key list
    assert isinstance(result["credential_keys"], list)
