from __future__ import annotations

from fastmcp import FastMCP

from mcp_server.tool_registry import MCPToolSpec


def _register_add_tool(mcp: FastMCP) -> None:
    @mcp.tool
    def add(a: float, b: float) -> float:
        """Add two numbers."""
        return float(a) + float(b)


def _register_substract_tool(mcp: FastMCP) -> None:
    @mcp.tool
    def substract(a: float, b: float) -> float:
        """Subtract b from a. Kept as 'substract' for API compatibility."""
        return float(a) - float(b)


TOOL_SPECS = [
    MCPToolSpec(
        name="add",
        description="Add two numeric values",
        register=_register_add_tool,
        version="1.0.0",
        tags=("core", "math", "sample"),
        risk_level="low",
    ),
    MCPToolSpec(
        name="substract",
        description="Subtract second value from first",
        register=_register_substract_tool,
        version="1.0.0",
        tags=("core", "math", "sample"),
        risk_level="low",
    ),
]
