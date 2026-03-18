from typing import Any
from pydantic import BaseModel


class PackageDisableUpdate(BaseModel):
    disabled: bool


class PackageRegisterRequest(BaseModel):
    name: str
    version: str
    description: str | None = None
    language: str | None = None
    entrypoint: str | None = None
    timeout_seconds: int = 60
    filename: str | None = None
    runtime_mode: str | None = None
    deployment: str | None = None
    restart_policy: str | None = None
    daemon_auto_start: bool | None = None
    exposed_port: int | None = None
    schedule_enabled: bool | None = None
    schedule_type: str | None = None
    schedule_config: dict[str, Any] | None = None
    secret_keys: list[str] | None = None
    environment: dict[str, Any] | None = None
    llm_provider: dict[str, Any] | None = None
    tool_bindings: list[dict[str, Any]] | None = None
    manifest_metadata: dict[str, Any] | None = None

class PackageScheduleUpdate(BaseModel):
    schedule_enables: bool
    schedule_type: str | None = None  # e.g., 'cron', 'interval'
    schedule_congig: dict | None = None  # e.g., {'cron': '0 0 * * *'} or {'interval': '1h'}    

class DemonAutoStartUpdate(BaseModel):
    deamon_auto_restart: bool

    