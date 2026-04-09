from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi import Header, HTTPException

from schemas.mcp_registry import MCPToolRegistryUpsertRequest, MCPToolSecretUpsertRequest
from services import mcp_client_service, mcp_tool_registry_service
from utils import dependency as dependencies
from utils.logger import get_logger, log_event


router = APIRouter(prefix="/mcp/registry", tags=["mcp-registry"])
LOGGER = get_logger("api.routers.mcp_registry")


def _validate_secret_resolver_token(token: str | None) -> None:
    expected = (os.getenv("MCP_SECRET_RESOLVER_TOKEN", "") or "").strip()
    if not expected:
        return
    if (token or "").strip() != expected:
        raise HTTPException(status_code=403, detail="Invalid MCP secret resolver token")


@router.get("/tools")
def list_registered_tools():
    with dependencies.db_session() as db:
        tools = mcp_tool_registry_service.list_mcp_tools(db)
        payload = [mcp_tool_registry_service.serialize_tool(tool) for tool in tools]
        log_event(LOGGER, 20, "mcp.registry.tools.listed", "Listed MCP registry tools", tool_count=len(payload))
        return payload


@router.post("/tools/sync")
def sync_registered_tools_from_mcp_server():
    with dependencies.db_session() as db:
        discovered = mcp_client_service.list_mcp_tools()
        source_tools = [
            {
                "tool_name": item.name,
                "description": item.description,
            }
            for item in (discovered.tools or [])
            if (item.name or "").strip()
        ]
        result = mcp_tool_registry_service.register_tools_if_missing(db, source_tools)
        log_event(
            LOGGER,
            20,
            "mcp.registry.tools.synced",
            "Synced MCP tools from MCP server into registry",
            discovered_count=len(source_tools),
            registered_count=result.get("registered_count", 0),
            skipped_count=result.get("skipped_count", 0),
        )
        return result


@router.get("/tools/{tool_name}")
def get_registered_tool(tool_name: str):
    with dependencies.db_session() as db:
        tool = mcp_tool_registry_service.get_mcp_tool_or_404(db, tool_name)
        payload = mcp_tool_registry_service.serialize_tool(tool)
        log_event(LOGGER, 20, "mcp.registry.tool.retrieved", "Retrieved MCP registry tool", tool_name=payload["tool_name"])
        return payload


@router.post("/tools", status_code=201)
def upsert_registered_tool(body: MCPToolRegistryUpsertRequest):
    with dependencies.db_session() as db:
        tool, created = mcp_tool_registry_service.upsert_mcp_tool(
            db,
            tool_name=body.tool_name,
            description=body.description,
            enabled=body.enabled,
            required_secret_keys=body.required_secret_keys,
        )
        payload = mcp_tool_registry_service.serialize_tool(tool)
        log_event(
            LOGGER,
            20,
            "mcp.registry.tool.upserted",
            "Upserted MCP registry tool",
            tool_name=payload["tool_name"],
            created=created,
        )
        return payload


@router.put("/tools/{tool_name}")
def update_registered_tool(tool_name: str, body: MCPToolRegistryUpsertRequest):
    with dependencies.db_session() as db:
        tool, _created = mcp_tool_registry_service.upsert_mcp_tool(
            db,
            tool_name=tool_name,
            description=body.description,
            enabled=body.enabled,
            required_secret_keys=body.required_secret_keys,
        )
        payload = mcp_tool_registry_service.serialize_tool(tool)
        log_event(LOGGER, 20, "mcp.registry.tool.updated", "Updated MCP registry tool", tool_name=payload["tool_name"])
        return payload


@router.delete("/tools/{tool_name}", status_code=204)
def delete_registered_tool(tool_name: str):
    with dependencies.db_session() as db:
        mcp_tool_registry_service.delete_mcp_tool(db, tool_name)
        log_event(LOGGER, 20, "mcp.registry.tool.deleted", "Deleted MCP registry tool", tool_name=tool_name)


@router.get("/tools/{tool_name}/secrets")
def list_registered_tool_secrets(tool_name: str):
    with dependencies.db_session() as db:
        tool, secrets = mcp_tool_registry_service.list_tool_secrets(db, tool_name)
        payload = [mcp_tool_registry_service.serialize_secret(tool.tool_name, secret) for secret in secrets]
        log_event(
            LOGGER,
            20,
            "mcp.registry.tool.secrets.listed",
            "Listed MCP registry tool secrets",
            tool_name=tool.tool_name,
            secret_count=len(payload),
        )
        return payload


@router.post("/tools/{tool_name}/secrets", status_code=201)
def upsert_registered_tool_secret(tool_name: str, body: MCPToolSecretUpsertRequest):
    with dependencies.db_session() as db:
        secret, created = mcp_tool_registry_service.upsert_tool_secret(db, tool_name, body.key_name, body.value)
        tool = mcp_tool_registry_service.get_mcp_tool_or_404(db, tool_name)
        payload = mcp_tool_registry_service.serialize_secret(tool.tool_name, secret)
        log_event(
            LOGGER,
            20,
            "mcp.registry.tool.secret.upserted",
            "Upserted MCP registry tool secret",
            tool_name=tool.tool_name,
            key_name=payload["key_name"],
            created=created,
        )
        return payload


@router.delete("/tools/{tool_name}/secrets/{key_name}", status_code=204)
def delete_registered_tool_secret(tool_name: str, key_name: str):
    with dependencies.db_session() as db:
        mcp_tool_registry_service.delete_tool_secret(db, tool_name, key_name)
        log_event(
            LOGGER,
            20,
            "mcp.registry.tool.secret.deleted",
            "Deleted MCP registry tool secret",
            tool_name=tool_name,
            key_name=key_name,
        )


@router.get("/tools/{tool_name}/secrets/{key_name}/resolve")
def resolve_registered_tool_secret(
    tool_name: str,
    key_name: str,
    x_mcp_secret_token: str | None = Header(default=None),
):
    _validate_secret_resolver_token(x_mcp_secret_token)

    with dependencies.db_session() as db:
        value = mcp_tool_registry_service.resolve_tool_secret_value(db, tool_name, key_name)
        log_event(
            LOGGER,
            20,
            "mcp.registry.tool.secret.resolved",
            "Resolved MCP registry tool secret for internal runtime usage",
            tool_name=tool_name,
            key_name=key_name,
        )
        return {
            "tool_name": tool_name,
            "key_name": key_name,
            "value": value,
        }
