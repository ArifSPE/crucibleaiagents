from fastapi import APIRouter

from schemas.mcp import MCPToolInvokeRequest
from services.mcp_client_service import list_mcp_tools, call_mcp_tool, get_mcp_health
from utils.logger import get_logger, log_event


router = APIRouter(prefix="/mcp", tags=["mcp"])
LOGGER = get_logger("api.routers.mcp")


@router.get("/health")
def mcp_health() -> dict:
    health = get_mcp_health()
    log_event(LOGGER, 20, "mcp.health.checked", "Checked MCP server health", status=health.get("status"))
    return health


@router.get("/tools")
def get_tools():
    response = list_mcp_tools()
    log_event(LOGGER, 20, "mcp.tools.listed", "Listed MCP tools", tool_count=len(response.tools))
    return response


@router.post("/tools/{tool_name}/invoke")
def invoke_tool(tool_name: str, body: MCPToolInvokeRequest):
    response = call_mcp_tool(tool_name, body.arguments)
    log_event(LOGGER, 20, "mcp.tool.invoked", "Invoked MCP tool via API", tool_name=tool_name, is_error=response.is_error)
    return response
