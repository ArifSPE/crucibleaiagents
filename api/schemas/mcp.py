from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MCPToolInfo(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class MCPToolsListResponse(BaseModel):
    server_url: str
    tools: list[MCPToolInfo] = Field(default_factory=list)


class MCPToolInvokeRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class MCPToolInvokeResponse(BaseModel):
    tool_name: str
    content: Any = None
    is_error: bool = False
    raw_result: dict[str, Any] = Field(default_factory=dict)
