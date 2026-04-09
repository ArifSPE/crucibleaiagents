from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class MCPToolRegistryUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool = True
    required_secret_keys: list[str] = Field(default_factory=list)


class MCPToolRegistryResponse(BaseModel):
    id: int
    tool_name: str
    description: str | None = None
    enabled: bool
    required_secret_keys: list[str] = Field(default_factory=list)
    configured_secret_keys: list[str] = Field(default_factory=list)
    missing_secret_keys: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MCPToolSecretUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_name: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1, max_length=20000)


class MCPToolSecretResponse(BaseModel):
    id: int
    tool_name: str
    key_name: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
