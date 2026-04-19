from schemas.mcp import (
    MCPPromptGetResponse,
    MCPPromptInfo,
    MCPResourceInfo,
    MCPResourceReadResponse,
    MCPToolInfo,
    MCPToolInvokeResponse,
    MCPToolsListResponse,
    MCPPromptsListResponse,
    MCPResourcesListResponse,
)
import routers.mcp as mcp_router


def test_mcp_health(client, monkeypatch):
    monkeypatch.setattr(
        mcp_router,
        "get_mcp_health",
        lambda: {
            "status": "ok",
            "server_url": "http://mcp_server:9001/mcp",
            "tool_count": 2,
        },
    )

    response = client.get("/mcp/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["tool_count"] == 2


def test_mcp_list_tools(client, monkeypatch):
    monkeypatch.setattr(
        mcp_router,
        "list_mcp_tools",
        lambda: MCPToolsListResponse(
            server_url="http://mcp_server:9001/mcp",
            tools=[
                MCPToolInfo(name="ping", description="health", input_schema={"type": "object"}),
                MCPToolInfo(name="analyze_text", description="analysis", input_schema={"type": "object"}),
            ],
        ),
    )

    response = client.get("/mcp/tools")
    assert response.status_code == 200
    payload = response.json()
    assert payload["server_url"] == "http://mcp_server:9001/mcp"
    assert len(payload["tools"]) == 2
    assert payload["tools"][0]["name"] == "ping"


def test_mcp_invoke_tool(client, monkeypatch):
    def _fake_call(tool_name: str, arguments: dict):
        assert tool_name == "ping"
        assert arguments == {"message": "hello"}
        return MCPToolInvokeResponse(
            tool_name=tool_name,
            content=[{"type": "text", "text": "pong: hello"}],
            is_error=False,
            raw_result={"content": [{"type": "text", "text": "pong: hello"}], "isError": False},
        )

    monkeypatch.setattr(mcp_router, "call_mcp_tool", _fake_call)

    response = client.post("/mcp/tools/ping/invoke", json={"arguments": {"message": "hello"}})
    assert response.status_code == 200
    payload = response.json()
    assert payload["tool_name"] == "ping"
    assert payload["is_error"] is False


def test_mcp_list_resources(client, monkeypatch):
    monkeypatch.setattr(
        mcp_router,
        "list_mcp_resources",
        lambda: MCPResourcesListResponse(
            server_url="http://mcp_server:9001/mcp",
            resources=[
                MCPResourceInfo(
                    uri="file://workspace/sample.txt",
                    name="sample.txt",
                    description="Workspace file",
                    mime_type="text/plain",
                )
            ],
        ),
    )

    response = client.get("/mcp/resources")
    assert response.status_code == 200
    payload = response.json()
    assert payload["server_url"] == "http://mcp_server:9001/mcp"
    assert payload["resources"][0]["uri"] == "file://workspace/sample.txt"


def test_mcp_read_resource(client, monkeypatch):
    def _fake_read(uri: str):
        assert uri == "file://workspace/sample.txt"
        return MCPResourceReadResponse(
            uri=uri,
            contents=[{"mimeType": "text/plain", "text": "hello world"}],
            raw_result={"contents": [{"mimeType": "text/plain", "text": "hello world"}]},
        )

    monkeypatch.setattr(mcp_router, "read_mcp_resource", _fake_read)

    response = client.get("/mcp/resources/read", params={"uri": "file://workspace/sample.txt"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["uri"] == "file://workspace/sample.txt"
    assert payload["contents"][0]["text"] == "hello world"


def test_mcp_list_prompts(client, monkeypatch):
    monkeypatch.setattr(
        mcp_router,
        "list_mcp_prompts",
        lambda: MCPPromptsListResponse(
            server_url="http://mcp_server:9001/mcp",
            prompts=[
                MCPPromptInfo(
                    name="summarize_workspace_file",
                    description="Summarize a workspace file",
                    arguments=[{"name": "filepath", "required": True}],
                )
            ],
        ),
    )

    response = client.get("/mcp/prompts")
    assert response.status_code == 200
    payload = response.json()
    assert payload["prompts"][0]["name"] == "summarize_workspace_file"


def test_mcp_render_prompt(client, monkeypatch):
    def _fake_get(name: str, arguments: dict):
        assert name == "summarize_workspace_file"
        assert arguments == {"filepath": "notes.txt"}
        return MCPPromptGetResponse(
            name=name,
            description="Summarize a workspace file",
            messages=[{"role": "user", "content": {"type": "text", "text": "Summarize notes.txt"}}],
            raw_result={"messages": [{"role": "user", "content": {"type": "text", "text": "Summarize notes.txt"}}]},
        )

    monkeypatch.setattr(mcp_router, "get_mcp_prompt", _fake_get)

    response = client.post("/mcp/prompts/summarize_workspace_file/render", json={"arguments": {"filepath": "notes.txt"}})
    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "summarize_workspace_file"
    assert payload["messages"][0]["role"] == "user"
