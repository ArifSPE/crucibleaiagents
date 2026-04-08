from schemas.mcp import MCPToolsListResponse, MCPToolInfo, MCPToolInvokeResponse
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
