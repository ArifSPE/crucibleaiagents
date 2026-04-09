from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from schemas.model import MCPToolRegistry, MCPToolSecret
from utils.logger import get_logger, log_event
from utils.secrets_manager import get_secrets_manager


LOGGER = get_logger("api.services.mcp_tool_registry_service")


def _normalize_tool_name(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="tool_name is required")
    return cleaned


def _normalize_secret_key(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="key_name is required")
    return cleaned


def _normalize_required_secret_keys(keys: list[str] | None) -> list[str]:
    if not keys:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in keys:
        key = _normalize_secret_key(item)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(key)
    return normalized


def get_mcp_tool_or_404(db: Session, tool_name: str) -> MCPToolRegistry:
    normalized_name = _normalize_tool_name(tool_name)
    tool = db.query(MCPToolRegistry).filter(MCPToolRegistry.tool_name == normalized_name).first()
    if not tool:
        raise HTTPException(status_code=404, detail=f"MCP tool '{normalized_name}' is not registered")
    return tool


def serialize_tool(tool: MCPToolRegistry) -> dict[str, Any]:
    required = _normalize_required_secret_keys(tool.required_secret_keys or [])
    configured = sorted([secret.key_name for secret in (tool.secrets or []) if secret and secret.key_name])
    configured_set = set(configured)
    missing = [key for key in required if key not in configured_set]

    return {
        "id": tool.id,
        "tool_name": tool.tool_name,
        "description": tool.description,
        "enabled": bool(tool.enabled),
        "required_secret_keys": required,
        "configured_secret_keys": configured,
        "missing_secret_keys": missing,
        "created_at": tool.created_at,
        "updated_at": tool.updated_at,
    }


def serialize_secret(tool_name: str, secret: MCPToolSecret) -> dict[str, Any]:
    return {
        "id": secret.id,
        "tool_name": tool_name,
        "key_name": secret.key_name,
        "created_at": secret.created_at,
        "updated_at": secret.updated_at,
    }


def list_mcp_tools(db: Session) -> list[MCPToolRegistry]:
    return db.query(MCPToolRegistry).order_by(MCPToolRegistry.tool_name.asc()).all()


def register_tools_if_missing(
    db: Session,
    tools: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create registry rows only for previously unseen tools.

    Existing tools are intentionally skipped and never mutated.
    """
    existing = {row.tool_name for row in db.query(MCPToolRegistry.tool_name).all()}

    registered_tools: list[str] = []
    skipped_tools: list[str] = []
    seen_in_batch: set[str] = set()

    for item in tools:
        tool_name = _normalize_tool_name(str(item.get("tool_name") or ""))
        description = str(item.get("description") or "") or None

        # Skip duplicates both from DB and from repeated names in the same sync payload.
        if tool_name in existing or tool_name in seen_in_batch:
            skipped_tools.append(tool_name)
            continue

        seen_in_batch.add(tool_name)
        db.add(
            MCPToolRegistry(
                tool_name=tool_name,
                description=description,
                enabled=True,
                required_secret_keys=[],
            )
        )
        registered_tools.append(tool_name)

    db.commit()

    log_event(
        LOGGER,
        20,
        "mcp.registry.tools.synced",
        "Synced MCP tools into registry with duplicate skip policy",
        registered_count=len(registered_tools),
        skipped_count=len(skipped_tools),
    )

    return {
        "registered_count": len(registered_tools),
        "skipped_count": len(skipped_tools),
        "registered_tools": registered_tools,
        "skipped_tools": skipped_tools,
    }


def upsert_mcp_tool(
    db: Session,
    *,
    tool_name: str,
    description: str | None,
    enabled: bool,
    required_secret_keys: list[str] | None,
) -> tuple[MCPToolRegistry, bool]:
    normalized_name = _normalize_tool_name(tool_name)
    normalized_required = _normalize_required_secret_keys(required_secret_keys)

    tool = db.query(MCPToolRegistry).filter(MCPToolRegistry.tool_name == normalized_name).first()
    created = False
    if tool is None:
        tool = MCPToolRegistry(
            tool_name=normalized_name,
            description=description,
            enabled=bool(enabled),
            required_secret_keys=normalized_required,
        )
        db.add(tool)
        created = True
    else:
        tool.description = description
        tool.enabled = bool(enabled)
        tool.required_secret_keys = normalized_required

    db.commit()
    db.refresh(tool)

    log_event(
        LOGGER,
        20,
        "mcp.registry.tool.upserted",
        "Upserted MCP tool registry record",
        tool_name=normalized_name,
        created=created,
        enabled=bool(tool.enabled),
        required_secret_key_count=len(normalized_required),
    )

    return tool, created


def delete_mcp_tool(db: Session, tool_name: str) -> None:
    tool = get_mcp_tool_or_404(db, tool_name)
    db.delete(tool)
    db.commit()

    log_event(
        LOGGER,
        20,
        "mcp.registry.tool.deleted",
        "Deleted MCP tool registry record",
        tool_name=tool.tool_name,
    )


def upsert_tool_secret(db: Session, tool_name: str, key_name: str, value: str) -> tuple[MCPToolSecret, bool]:
    tool = get_mcp_tool_or_404(db, tool_name)
    normalized_key = _normalize_secret_key(key_name)

    try:
        encrypted = get_secrets_manager().encrypt(value)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=f"Encryption error: {exc}")

    secret = (
        db.query(MCPToolSecret)
        .filter(MCPToolSecret.tool_id == tool.id, MCPToolSecret.key_name == normalized_key)
        .first()
    )

    created = False
    if secret is None:
        secret = MCPToolSecret(tool_id=tool.id, key_name=normalized_key, encrypted_value=encrypted)
        db.add(secret)
        created = True
    else:
        secret.encrypted_value = encrypted

    db.commit()
    db.refresh(secret)

    log_event(
        LOGGER,
        20,
        "mcp.registry.secret.upserted",
        "Upserted MCP tool secret",
        tool_name=tool.tool_name,
        key_name=normalized_key,
        created=created,
    )
    return secret, created


def list_tool_secrets(db: Session, tool_name: str) -> tuple[MCPToolRegistry, list[MCPToolSecret]]:
    tool = get_mcp_tool_or_404(db, tool_name)
    secrets = (
        db.query(MCPToolSecret)
        .filter(MCPToolSecret.tool_id == tool.id)
        .order_by(MCPToolSecret.key_name.asc())
        .all()
    )
    return tool, secrets


def delete_tool_secret(db: Session, tool_name: str, key_name: str) -> None:
    tool = get_mcp_tool_or_404(db, tool_name)
    normalized_key = _normalize_secret_key(key_name)
    secret = (
        db.query(MCPToolSecret)
        .filter(MCPToolSecret.tool_id == tool.id, MCPToolSecret.key_name == normalized_key)
        .first()
    )
    if not secret:
        raise HTTPException(status_code=404, detail=f"Secret '{normalized_key}' is not configured for tool '{tool.tool_name}'")

    db.delete(secret)
    db.commit()

    log_event(
        LOGGER,
        20,
        "mcp.registry.secret.deleted",
        "Deleted MCP tool secret",
        tool_name=tool.tool_name,
        key_name=normalized_key,
    )


def resolve_tool_secret_value(db: Session, tool_name: str, key_name: str) -> str:
    tool = get_mcp_tool_or_404(db, tool_name)
    normalized_key = _normalize_secret_key(key_name)
    secret = (
        db.query(MCPToolSecret)
        .filter(MCPToolSecret.tool_id == tool.id, MCPToolSecret.key_name == normalized_key)
        .first()
    )
    if not secret:
        raise HTTPException(status_code=404, detail=f"Secret '{normalized_key}' is not configured for tool '{tool.tool_name}'")

    try:
        value = get_secrets_manager().decrypt(secret.encrypted_value)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=f"Decryption error: {exc}")

    if not value:
        raise HTTPException(status_code=404, detail=f"Secret '{normalized_key}' is empty for tool '{tool.tool_name}'")

    log_event(
        LOGGER,
        20,
        "mcp.registry.secret.resolved",
        "Resolved MCP tool secret value for internal runtime usage",
        tool_name=tool.tool_name,
        key_name=normalized_key,
    )
    return value


def get_tool_secret_status_map(db: Session, tool_names: list[str]) -> dict[str, dict[str, Any]]:
    if not tool_names:
        return {}

    normalized_names = [_normalize_tool_name(name) for name in tool_names if (name or "").strip()]
    if not normalized_names:
        return {}

    rows = db.query(MCPToolRegistry).filter(MCPToolRegistry.tool_name.in_(normalized_names)).all()
    mapping: dict[str, dict[str, Any]] = {}
    for tool in rows:
        serialized = serialize_tool(tool)
        mapping[tool.tool_name] = {
            "enabled": bool(serialized.get("enabled")),
            "missing_secret_keys": serialized.get("missing_secret_keys", []),
        }
    return mapping
