from fastapi import APIRouter

from schemas.mcp import MCPPromptGetRequest, MCPToolInvokeRequest
from services.mcp_client_service import (
    call_mcp_tool,
    get_mcp_health,
    get_mcp_prompt,
    list_mcp_prompts,
    list_mcp_resources,
    list_mcp_tools,
    read_mcp_resource,
)
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


@router.get("/resources")
def get_resources():
    response = list_mcp_resources()
    log_event(LOGGER, 20, "mcp.resources.listed", "Listed MCP resources", resource_count=len(response.resources))
    return response


@router.get("/resources/read")
def get_resource_content(uri: str):
    response = read_mcp_resource(uri)
    log_event(LOGGER, 20, "mcp.resource.read", "Read MCP resource via API", uri=uri, content_count=len(response.contents))
    return response


@router.get("/prompts")
def get_prompts():
    response = list_mcp_prompts()
    log_event(LOGGER, 20, "mcp.prompts.listed", "Listed MCP prompts", prompt_count=len(response.prompts))
    return response


@router.post("/prompts/{prompt_name}/render")
def render_prompt(prompt_name: str, body: MCPPromptGetRequest):
    response = get_mcp_prompt(prompt_name, body.arguments)
    log_event(LOGGER, 20, "mcp.prompt.rendered", "Rendered MCP prompt via API", prompt_name=prompt_name, message_count=len(response.messages))
    return response
