from __future__ import annotations

import logging
import os

from fastmcp import FastMCP
from starlette.responses import JSONResponse

from mcp_server.tool_registry import register_tools

mcp = FastMCP("Crucible MCP Server")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s")
LOGGER = logging.getLogger("mcp_server")

REGISTERED_TOOL_SPECS = register_tools(mcp)


@mcp.custom_route("/health", methods=["GET"])
async def health(_: object) -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "service": "mcp-server",
            "registered_tool_count": len(REGISTERED_TOOL_SPECS),
            "registered_tools": [spec.name for spec in REGISTERED_TOOL_SPECS],
        }
    )


if __name__ == "__main__":
    host = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_SERVER_PORT", "9001"))
    path = os.getenv("MCP_SERVER_PATH", "/mcp")
    LOGGER.info("Starting MCP server host=%s port=%s path=%s tools=%s", host, port, path, [spec.name for spec in REGISTERED_TOOL_SPECS])
    mcp.run(transport="http", host=host, port=port, path=path, stateless_http=True)
