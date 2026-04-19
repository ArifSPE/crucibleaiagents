def test_create_and_get_mcp_registry_tool(client):
    create_resp = client.post(
        "/mcp/registry/tools",
        json={
            "tool_name": "tavily_search",
            "description": "Search the web",
            "enabled": True,
            "required_secret_keys": ["TAVILY_API_KEY"],
        },
    )
    assert create_resp.status_code == 201
    payload = create_resp.json()
    assert payload["tool_name"] == "tavily_search"
    assert payload["required_secret_keys"] == ["TAVILY_API_KEY"]
    assert payload["missing_secret_keys"] == ["TAVILY_API_KEY"]

    get_resp = client.get("/mcp/registry/tools/tavily_search")
    assert get_resp.status_code == 200
    assert get_resp.json()["tool_name"] == "tavily_search"


def test_upsert_mcp_registry_tool_secret_does_not_leak_value(client):
    client.post(
        "/mcp/registry/tools",
        json={
            "tool_name": "tavily_search",
            "description": "Search the web",
            "enabled": True,
            "required_secret_keys": ["TAVILY_API_KEY"],
        },
    )

    secret_resp = client.post(
        "/mcp/registry/tools/tavily_search/secrets",
        json={
            "key_name": "TAVILY_API_KEY",
            "value": "super-secret-value",
        },
    )
    assert secret_resp.status_code == 201
    assert "super-secret-value" not in secret_resp.text

    list_resp = client.get("/mcp/registry/tools/tavily_search/secrets")
    assert list_resp.status_code == 200
    secrets = list_resp.json()
    assert len(secrets) == 1
    assert secrets[0]["key_name"] == "TAVILY_API_KEY"
    assert "super-secret-value" not in list_resp.text

    tool_resp = client.get("/mcp/registry/tools/tavily_search")
    assert tool_resp.status_code == 200
    tool_payload = tool_resp.json()
    assert tool_payload["missing_secret_keys"] == []
    assert "super-secret-value" not in str(tool_payload)


def test_delete_mcp_registry_tool_secret(client):
    client.post(
        "/mcp/registry/tools",
        json={
            "tool_name": "web_service_call",
            "description": "Call web service",
            "enabled": True,
            "required_secret_keys": ["WEB_API_KEY"],
        },
    )
    client.post(
        "/mcp/registry/tools/web_service_call/secrets",
        json={
            "key_name": "WEB_API_KEY",
            "value": "abc123",
        },
    )

    del_resp = client.delete("/mcp/registry/tools/web_service_call/secrets/WEB_API_KEY")
    assert del_resp.status_code == 204

    tool_resp = client.get("/mcp/registry/tools/web_service_call")
    assert tool_resp.status_code == 200
    assert tool_resp.json()["missing_secret_keys"] == ["WEB_API_KEY"]


def test_resolve_mcp_registry_tool_secret_endpoint_disabled_without_token_config(client, monkeypatch):
    client.post(
        "/mcp/registry/tools",
        json={
            "tool_name": "tavily_search",
            "description": "Search tool",
            "enabled": True,
            "required_secret_keys": ["TAVILY_API_KEY"],
        },
    )
    client.post(
        "/mcp/registry/tools/tavily_search/secrets",
        json={
            "key_name": "TAVILY_API_KEY",
            "value": "secret-xyz",
        },
    )

    monkeypatch.delenv("MCP_SECRET_RESOLVER_TOKEN", raising=False)

    resolve_resp = client.get("/mcp/registry/tools/tavily_search/secrets/TAVILY_API_KEY/resolve")
    assert resolve_resp.status_code == 503
    assert "disabled" in resolve_resp.json()["detail"].lower()


def test_resolve_mcp_registry_tool_secret_requires_token_when_configured(client, monkeypatch):
    client.post(
        "/mcp/registry/tools",
        json={
            "tool_name": "tavily_search",
            "description": "Search tool",
            "enabled": True,
            "required_secret_keys": ["TAVILY_API_KEY"],
        },
    )
    client.post(
        "/mcp/registry/tools/tavily_search/secrets",
        json={
            "key_name": "TAVILY_API_KEY",
            "value": "secret-abc",
        },
    )

    monkeypatch.setenv("MCP_SECRET_RESOLVER_TOKEN", "resolver-token")

    forbidden_resp = client.get("/mcp/registry/tools/tavily_search/secrets/TAVILY_API_KEY/resolve")
    assert forbidden_resp.status_code == 403

    allowed_resp = client.get(
        "/mcp/registry/tools/tavily_search/secrets/TAVILY_API_KEY/resolve",
        headers={"x-mcp-secret-token": "resolver-token"},
    )
    assert allowed_resp.status_code == 200
    assert allowed_resp.json()["value"] == "secret-abc"


def test_sync_registry_tools_skips_existing_without_overwrite(client, db, monkeypatch):
    from schemas.mcp import MCPToolInfo, MCPToolsListResponse
    from schemas.model import MCPToolRegistry
    import routers.mcp_registry as mcp_registry_router

    db.add(
        MCPToolRegistry(
            tool_name="ping",
            description="original description",
            enabled=True,
            required_secret_keys=[],
        )
    )
    db.commit()

    monkeypatch.setattr(
        mcp_registry_router.mcp_client_service,
        "list_mcp_tools",
        lambda: MCPToolsListResponse(
            server_url="http://mcp_server:9001/mcp",
            tools=[
                MCPToolInfo(name="ping", description="updated from source", input_schema={}),
                MCPToolInfo(name="analyze_text", description="Analyze text", input_schema={}),
            ],
        ),
    )

    resp = client.post("/mcp/registry/tools/sync")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["registered_count"] == 1
    assert payload["skipped_count"] == 1
    assert payload["registered_tools"] == ["analyze_text"]
    assert payload["skipped_tools"] == ["ping"]

    ping_row = db.query(MCPToolRegistry).filter(MCPToolRegistry.tool_name == "ping").first()
    assert ping_row is not None
    assert ping_row.description == "original description"


def test_sync_registry_tools_skips_duplicates_in_single_batch(client, monkeypatch):
    from schemas.mcp import MCPToolInfo, MCPToolsListResponse
    import routers.mcp_registry as mcp_registry_router

    monkeypatch.setattr(
        mcp_registry_router.mcp_client_service,
        "list_mcp_tools",
        lambda: MCPToolsListResponse(
            server_url="http://mcp_server:9001/mcp",
            tools=[
                MCPToolInfo(name="ping", description="first", input_schema={}),
                MCPToolInfo(name="ping", description="duplicate", input_schema={}),
            ],
        ),
    )

    resp = client.post("/mcp/registry/tools/sync")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["registered_count"] == 1
    assert payload["skipped_count"] == 1
    assert payload["registered_tools"] == ["ping"]
    assert payload["skipped_tools"] == ["ping"]
