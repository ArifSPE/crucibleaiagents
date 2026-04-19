from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

import httpx
from fastapi import HTTPException

from schemas.mcp import (
    MCPPromptArgumentInfo,
    MCPPromptGetResponse,
    MCPPromptInfo,
    MCPPromptsListResponse,
    MCPResourceInfo,
    MCPResourceReadResponse,
    MCPResourcesListResponse,
    MCPToolInfo,
    MCPToolsListResponse,
    MCPToolInvokeResponse,
)
from utils.config import (
    MCP_SERVER_URL,
    MCP_CLIENT_TIMEOUT_SECONDS,
    MCP_SERVER_AUTH_TOKEN,
    MCP_CLIENT_ORCHESTRATION,
)
from utils.logger import get_logger, log_event, log_exception


LOGGER = get_logger("api.services.mcp_client_service")
_ALLOWED_MODES = {"auto", "jsonrpc", "adapter"}


def _build_headers() -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if MCP_SERVER_AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {MCP_SERVER_AUTH_TOKEN}"
    return headers


def _resolve_client_mode() -> str:
    mode = (MCP_CLIENT_ORCHESTRATION or "auto").strip().lower()
    if mode not in _ALLOWED_MODES:
        log_event(
            LOGGER,
            30,
            "mcp.client.mode.invalid",
            "Invalid MCP client orchestration mode; defaulting to auto",
            configured_mode=mode,
        )
        mode = "auto"

    if mode == "auto":
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient  # noqa: F401

            return "adapter"
        except Exception:
            return "jsonrpc"

    return mode


def _run_async(coro: Any) -> Any:
    """Run async code from sync service functions.

    FastAPI sync endpoints run in worker threads, where `asyncio.run` is safe.
    """
    return asyncio.run(coro)


def _extract_rpc_result(payload: dict[str, Any], method: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail=f"MCP server returned invalid payload for {method}")

    error_obj = payload.get("error")
    if isinstance(error_obj, dict):
        message = str(error_obj.get("message") or "MCP error")
        code = error_obj.get("code")
        raise HTTPException(status_code=502, detail=f"MCP {method} failed ({code}): {message}")

    result = payload.get("result")
    if not isinstance(result, dict):
        raise HTTPException(status_code=502, detail=f"MCP server returned no result for {method}")
    return result


def _parse_sse_json_payload(raw_text: str) -> dict[str, Any]:
    """Extract JSON-RPC payload from streamable HTTP SSE response body."""
    candidates: list[dict[str, Any]] = []
    for line in (raw_text or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith("data:"):
            continue
        data_part = stripped[5:].strip()
        if not data_part:
            continue
        try:
            parsed = json.loads(data_part)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            candidates.append(parsed)

    # Prefer the last JSON object that looks like JSON-RPC response payload.
    for payload in reversed(candidates):
        if any(key in payload for key in ("result", "error", "jsonrpc")):
            return payload

    raise ValueError("No JSON-RPC payload found in SSE response")


def _rpc_call(method: str, params: dict[str, Any]) -> dict[str, Any]:
    request_id = str(uuid4())
    body = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params,
    }

    log_event(
        LOGGER,
        20,
        "mcp.rpc.call.start",
        "Calling MCP server",
        method=method,
        mcp_server_url=MCP_SERVER_URL,
        request_id=request_id,
    )

    try:
        with httpx.Client(timeout=MCP_CLIENT_TIMEOUT_SECONDS) as client:
            response = client.post(MCP_SERVER_URL, json=body, headers=_build_headers())
    except httpx.TimeoutException:
        log_event(
            LOGGER,
            40,
            "mcp.rpc.call.timeout",
            "MCP server call timed out",
            method=method,
            timeout_seconds=MCP_CLIENT_TIMEOUT_SECONDS,
        )
        raise HTTPException(status_code=504, detail="MCP server request timed out")
    except httpx.HTTPError as exc:
        log_event(
            LOGGER,
            40,
            "mcp.rpc.call.connection_error",
            "Failed to connect to MCP server",
            method=method,
            error=str(exc),
        )
        raise HTTPException(status_code=502, detail=f"Failed to connect to MCP server: {exc}")

    if response.status_code >= 400:
        detail = (response.text or "MCP HTTP error")[:300]
        log_event(
            LOGGER,
            40,
            "mcp.rpc.call.http_error",
            "MCP server returned HTTP error",
            method=method,
            status_code=response.status_code,
            detail=detail,
        )
        raise HTTPException(status_code=502, detail=f"MCP server HTTP error ({response.status_code}): {detail}")

    content_type = (response.headers.get("content-type") or "").lower()
    try:
        if "text/event-stream" in content_type:
            payload = _parse_sse_json_payload(response.text)
        else:
            payload = response.json()
    except ValueError as exc:
        log_exception(
            LOGGER,
            "mcp.rpc.call.invalid_json",
            "MCP server returned invalid JSON",
            method=method,
            content_type=content_type,
            response_preview=(response.text or "")[:200],
            error=str(exc),
        )
        raise HTTPException(status_code=502, detail="MCP server returned invalid JSON")

    result = _extract_rpc_result(payload, method)
    log_event(
        LOGGER,
        20,
        "mcp.rpc.call.success",
        "MCP server call succeeded",
        method=method,
        request_id=request_id,
    )
    return result


def _get_adapter_client() -> Any:
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"langchain-mcp-adapters is unavailable: {exc}")

    server_config: dict[str, Any] = {
        "transport": "http",
        "url": MCP_SERVER_URL,
    }
    if MCP_SERVER_AUTH_TOKEN:
        server_config["headers"] = {"Authorization": f"Bearer {MCP_SERVER_AUTH_TOKEN}"}

    return MultiServerMCPClient({"platform_mcp": server_config})


def _tool_input_schema(tool_obj: Any) -> dict[str, Any]:
    args_schema = getattr(tool_obj, "args_schema", None)
    if args_schema is None:
        return {}

    try:
        if hasattr(args_schema, "model_json_schema"):
            return args_schema.model_json_schema()
        if hasattr(args_schema, "schema"):
            return args_schema.schema()
    except Exception:
        return {}
    return {}


async def _adapter_get_tools() -> list[Any]:
    client = _get_adapter_client()
    return await client.get_tools()


async def _adapter_call_tool(tool_name: str, arguments: dict[str, Any]) -> tuple[Any, list[Any]]:
    client = _get_adapter_client()
    tools = await client.get_tools()

    selected = None
    for tool in tools:
        if getattr(tool, "name", "") == tool_name:
            selected = tool
            break
    if selected is None:
        raise HTTPException(status_code=404, detail=f"MCP tool '{tool_name}' not found")

    if hasattr(selected, "ainvoke"):
        result = await selected.ainvoke(arguments or {})
    elif hasattr(selected, "invoke"):
        result = selected.invoke(arguments or {})
    else:
        raise HTTPException(status_code=500, detail=f"MCP tool '{tool_name}' is not invokable")

    return result, tools


def _adapter_list_mcp_tools() -> MCPToolsListResponse:
    log_event(LOGGER, 20, "mcp.adapter.list.start", "Listing MCP tools via adapter", mcp_server_url=MCP_SERVER_URL)
    try:
        tools_raw = _run_async(_adapter_get_tools())
    except HTTPException:
        raise
    except Exception as exc:
        log_exception(
            LOGGER,
            "mcp.adapter.list.failed",
            "Failed to list tools via adapter",
            error=str(exc),
        )
        raise HTTPException(status_code=502, detail=f"MCP adapter list failed: {exc}")

    tools: list[MCPToolInfo] = []
    for tool in tools_raw:
        tools.append(
            MCPToolInfo(
                name=str(getattr(tool, "name", "") or ""),
                description=str(getattr(tool, "description", "") or ""),
                input_schema=_tool_input_schema(tool),
            )
        )

    log_event(
        LOGGER,
        20,
        "mcp.adapter.list.success",
        "Listed tools via adapter",
        tool_count=len(tools),
        mcp_server_url=MCP_SERVER_URL,
    )
    return MCPToolsListResponse(server_url=MCP_SERVER_URL, tools=tools)


def _adapter_call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> MCPToolInvokeResponse:
    log_event(LOGGER, 20, "mcp.adapter.call.start", "Calling MCP tool via adapter", tool_name=tool_name)
    try:
        result, _tools = _run_async(_adapter_call_tool(tool_name, arguments))
    except HTTPException:
        raise
    except Exception as exc:
        log_exception(
            LOGGER,
            "mcp.adapter.call.failed",
            "Failed to call MCP tool via adapter",
            tool_name=tool_name,
            error=str(exc),
        )
        raise HTTPException(status_code=502, detail=f"MCP adapter call failed: {exc}")

    return MCPToolInvokeResponse(
        tool_name=tool_name,
        content=result,
        is_error=False,
        raw_result={"content": result, "adapter_mode": True},
    )


def _jsonrpc_list_mcp_tools() -> MCPToolsListResponse:
    result = _rpc_call("tools/list", {})

    tools_payload = result.get("tools") if isinstance(result, dict) else []
    tools: list[MCPToolInfo] = []
    if isinstance(tools_payload, list):
        for item in tools_payload:
            if not isinstance(item, dict):
                continue
            tools.append(
                MCPToolInfo(
                    name=str(item.get("name") or ""),
                    description=str(item.get("description") or ""),
                    input_schema=item.get("inputSchema") or item.get("input_schema") or {},
                )
            )

    log_event(
        LOGGER,
        20,
        "mcp.tools.listed",
        "Listed tools from MCP server",
        orchestration="jsonrpc",
        tool_count=len(tools),
        mcp_server_url=MCP_SERVER_URL,
    )
    return MCPToolsListResponse(server_url=MCP_SERVER_URL, tools=tools)


def _jsonrpc_call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> MCPToolInvokeResponse:
    result = _rpc_call(
        "tools/call",
        {
            "name": tool_name,
            "arguments": arguments or {},
        },
    )

    response = MCPToolInvokeResponse(
        tool_name=tool_name,
        content=result.get("content"),
        is_error=bool(result.get("isError") or result.get("is_error") or False),
        raw_result=result,
    )

    log_event(
        LOGGER,
        20,
        "mcp.tool.called",
        "Called MCP tool",
        orchestration="jsonrpc",
        tool_name=tool_name,
        is_error=response.is_error,
    )

    return response


def _normalize_prompt_arguments(arguments: Any) -> list[MCPPromptArgumentInfo | dict[str, Any]]:
    if not isinstance(arguments, list):
        return []

    normalized: list[MCPPromptArgumentInfo | dict[str, Any]] = []
    for item in arguments:
        if not isinstance(item, dict):
            continue
        normalized.append(
            MCPPromptArgumentInfo(
                name=str(item.get("name") or ""),
                description=str(item.get("description") or ""),
                required=bool(item.get("required") or False),
            )
        )
    return normalized


def list_mcp_resources() -> MCPResourcesListResponse:
    result = _rpc_call("resources/list", {})

    resources_payload = result.get("resources") if isinstance(result, dict) else []
    resources: list[MCPResourceInfo] = []
    if isinstance(resources_payload, list):
        for item in resources_payload:
            if not isinstance(item, dict):
                continue
            resources.append(
                MCPResourceInfo(
                    uri=str(item.get("uri") or ""),
                    name=str(item.get("name") or ""),
                    description=str(item.get("description") or ""),
                    mime_type=item.get("mimeType") or item.get("mime_type"),
                )
            )

    log_event(
        LOGGER,
        20,
        "mcp.resources.listed",
        "Listed MCP resources",
        resource_count=len(resources),
        mcp_server_url=MCP_SERVER_URL,
    )
    return MCPResourcesListResponse(server_url=MCP_SERVER_URL, resources=resources)


def read_mcp_resource(uri: str) -> MCPResourceReadResponse:
    normalized_uri = (uri or "").strip()
    if not normalized_uri:
        raise HTTPException(status_code=400, detail="uri is required")

    result = _rpc_call("resources/read", {"uri": normalized_uri})
    contents = result.get("contents") if isinstance(result, dict) else []
    if not isinstance(contents, list):
        contents = []

    response = MCPResourceReadResponse(
        uri=normalized_uri,
        contents=contents,
        raw_result=result,
    )

    log_event(
        LOGGER,
        20,
        "mcp.resource.read",
        "Read MCP resource",
        uri=normalized_uri,
        content_count=len(contents),
    )
    return response


def list_mcp_prompts() -> MCPPromptsListResponse:
    result = _rpc_call("prompts/list", {})

    prompts_payload = result.get("prompts") if isinstance(result, dict) else []
    prompts: list[MCPPromptInfo] = []
    if isinstance(prompts_payload, list):
        for item in prompts_payload:
            if not isinstance(item, dict):
                continue
            prompts.append(
                MCPPromptInfo(
                    name=str(item.get("name") or ""),
                    description=str(item.get("description") or ""),
                    arguments=_normalize_prompt_arguments(item.get("arguments")),
                )
            )

    log_event(
        LOGGER,
        20,
        "mcp.prompts.listed",
        "Listed MCP prompts",
        prompt_count=len(prompts),
        mcp_server_url=MCP_SERVER_URL,
    )
    return MCPPromptsListResponse(server_url=MCP_SERVER_URL, prompts=prompts)


def get_mcp_prompt(name: str, arguments: dict[str, Any]) -> MCPPromptGetResponse:
    prompt_name = (name or "").strip()
    if not prompt_name:
        raise HTTPException(status_code=400, detail="prompt name is required")

    result = _rpc_call(
        "prompts/get",
        {
            "name": prompt_name,
            "arguments": arguments or {},
        },
    )

    messages = result.get("messages") if isinstance(result, dict) else []
    if not isinstance(messages, list):
        messages = []

    response = MCPPromptGetResponse(
        name=prompt_name,
        description=str(result.get("description") or "") if isinstance(result, dict) else "",
        messages=messages,
        raw_result=result,
    )

    log_event(
        LOGGER,
        20,
        "mcp.prompt.rendered",
        "Rendered MCP prompt",
        prompt_name=prompt_name,
        message_count=len(messages),
    )
    return response


def list_mcp_tools() -> MCPToolsListResponse:
    mode = _resolve_client_mode()
    log_event(LOGGER, 20, "mcp.tools.list.mode_selected", "Selected MCP tool list orchestration mode", orchestration=mode)

    if mode == "adapter":
        return _adapter_list_mcp_tools()
    return _jsonrpc_list_mcp_tools()


def call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> MCPToolInvokeResponse:
    if not tool_name.strip():
        raise HTTPException(status_code=400, detail="tool_name is required")

    mode = _resolve_client_mode()
    log_event(LOGGER, 20, "mcp.tool.call.mode_selected", "Selected MCP tool call orchestration mode", orchestration=mode, tool_name=tool_name)

    if mode == "adapter":
        return _adapter_call_mcp_tool(tool_name, arguments)
    return _jsonrpc_call_mcp_tool(tool_name, arguments)


def get_mcp_health() -> dict[str, Any]:
    tools = list_mcp_tools()

    resource_count: int | None = None
    prompt_count: int | None = None
    try:
        resource_count = len(list_mcp_resources().resources)
    except HTTPException:
        resource_count = None
    try:
        prompt_count = len(list_mcp_prompts().prompts)
    except HTTPException:
        prompt_count = None

    return {
        "status": "ok",
        "server_url": tools.server_url,
        "tool_count": len(tools.tools),
        "resource_count": resource_count,
        "prompt_count": prompt_count,
    }
