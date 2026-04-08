from __future__ import annotations

import importlib
import logging
import os
import pkgutil
from dataclasses import dataclass, field
from typing import Callable, Iterable

from fastmcp import FastMCP


LOGGER = logging.getLogger("mcp_server.registry")


@dataclass(frozen=True)
class MCPToolSpec:
    name: str
    description: str
    register: Callable[[FastMCP], None]
    version: str = "1.0.0"
    tags: tuple[str, ...] = field(default_factory=tuple)
    enabled_by_default: bool = True
    risk_level: str = "low"


def _parse_csv_env(name: str) -> set[str]:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


def discover_tool_specs(package_name: str = "mcp_server.tools") -> list[MCPToolSpec]:
    specs: list[MCPToolSpec] = []
    package = importlib.import_module(package_name)

    for module_info in pkgutil.walk_packages(package.__path__, prefix=f"{package_name}."):
        if module_info.name.endswith(".__init__"):
            continue
        try:
            module = importlib.import_module(module_info.name)
        except Exception as exc:
            LOGGER.warning("Skipping MCP tool module %s due to import error: %s", module_info.name, exc)
            continue

        module_specs: Iterable[MCPToolSpec] = getattr(module, "TOOL_SPECS", [])
        for spec in module_specs:
            if not isinstance(spec, MCPToolSpec):
                LOGGER.warning("Ignoring invalid MCP tool spec in %s", module_info.name)
                continue
            specs.append(spec)

    return specs


def _apply_policy(specs: list[MCPToolSpec]) -> list[MCPToolSpec]:
    enabled = _parse_csv_env("MCP_ENABLED_TOOLS")
    disabled = _parse_csv_env("MCP_DISABLED_TOOLS")

    filtered: list[MCPToolSpec] = []
    for spec in specs:
        if enabled and spec.name not in enabled:
            LOGGER.info("Skipping MCP tool %s: not in MCP_ENABLED_TOOLS", spec.name)
            continue
        if spec.name in disabled:
            LOGGER.info("Skipping MCP tool %s: present in MCP_DISABLED_TOOLS", spec.name)
            continue
        if not spec.enabled_by_default and not enabled:
            LOGGER.info("Skipping MCP tool %s: disabled by default", spec.name)
            continue
        filtered.append(spec)

    return filtered


def register_tools(mcp: FastMCP) -> list[MCPToolSpec]:
    discovered_specs = discover_tool_specs()
    filtered_specs = _apply_policy(discovered_specs)

    seen_names: set[str] = set()
    registered_specs: list[MCPToolSpec] = []

    for spec in filtered_specs:
        if spec.name in seen_names:
            LOGGER.warning("Skipping duplicate MCP tool name: %s", spec.name)
            continue
        seen_names.add(spec.name)

        try:
            spec.register(mcp)
            registered_specs.append(spec)
            LOGGER.info(
                "Registered MCP tool name=%s version=%s tags=%s risk=%s",
                spec.name,
                spec.version,
                list(spec.tags),
                spec.risk_level,
            )
        except Exception as exc:
            LOGGER.exception("Failed to register MCP tool %s: %s", spec.name, exc)

    LOGGER.info(
        "MCP tool registration completed: discovered=%d registered=%d",
        len(discovered_specs),
        len(registered_specs),
    )
    return registered_specs
