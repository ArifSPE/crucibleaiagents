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


class MCPResourceInfo(BaseModel):
    uri: str
    name: str = ""
    description: str = ""
    mime_type: str | None = None


class MCPResourcesListResponse(BaseModel):
    server_url: str
    resources: list[MCPResourceInfo] = Field(default_factory=list)


class MCPResourceReadResponse(BaseModel):
    uri: str
    contents: list[dict[str, Any]] = Field(default_factory=list)
    raw_result: dict[str, Any] = Field(default_factory=dict)


class MCPPromptArgumentInfo(BaseModel):
    name: str
    description: str = ""
    required: bool = False


class MCPPromptInfo(BaseModel):
    name: str
    description: str = ""
    arguments: list[MCPPromptArgumentInfo | dict[str, Any]] = Field(default_factory=list)


class MCPPromptsListResponse(BaseModel):
    server_url: str
    prompts: list[MCPPromptInfo] = Field(default_factory=list)


class MCPPromptGetRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class MCPPromptGetResponse(BaseModel):
    name: str
    description: str = ""
    messages: list[dict[str, Any]] = Field(default_factory=list)
    raw_result: dict[str, Any] = Field(default_factory=dict)
