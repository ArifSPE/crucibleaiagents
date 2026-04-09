from __future__ import annotations

import os
from typing import Optional

import httpx


_CACHE: dict[tuple[str, str], str] = {}


def _resolver_base_url() -> str:
    return (os.getenv("MCP_SECRET_RESOLVER_BASE_URL", "http://api:8000") or "http://api:8000").rstrip("/")


def _resolver_timeout_seconds() -> int:
    raw = (os.getenv("MCP_SECRET_RESOLVER_TIMEOUT_SECONDS", "10") or "10").strip()
    try:
        return max(1, min(60, int(raw)))
    except ValueError:
        return 10


def _resolver_token() -> str:
    return (os.getenv("MCP_SECRET_RESOLVER_TOKEN", "") or "").strip()


def resolve_tool_secret(tool_name: str, key_name: str) -> Optional[str]:
    cache_key = (tool_name.strip(), key_name.strip())
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    url = f"{_resolver_base_url()}/mcp/registry/tools/{tool_name}/secrets/{key_name}/resolve"
    headers = {"Accept": "application/json"}
    token = _resolver_token()
    if token:
        headers["x-mcp-secret-token"] = token

    try:
        with httpx.Client(timeout=_resolver_timeout_seconds()) as client:
            response = client.get(url, headers=headers)
            if response.status_code >= 400:
                return None
            payload = response.json()
    except Exception:
        return None

    value = str(payload.get("value") or "") if isinstance(payload, dict) else ""
    if not value:
        return None

    _CACHE[cache_key] = value
    return value
