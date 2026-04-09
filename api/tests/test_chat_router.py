import pytest
from fastapi import HTTPException
from datetime import datetime, timedelta, timezone

from schemas.model import LlmProvider, LLMChatMemory, LLMChatSummary
from schemas.mcp import MCPToolInfo, MCPToolsListResponse, MCPToolInvokeResponse
import routers.chat as chat_router


def _create_provider(db, provider_name: str = "local_ollama") -> LlmProvider:
    provider = LlmProvider(provider=provider_name, description="test")
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return provider


def test_chat_provider_not_found(client):
    body = {
        "provider_name": "local_ollama",
        "message": "hello",
    }
    resp = client.post("/chat/99999", json=body)
    assert resp.status_code == 404


def test_chat_provider_name_mismatch(client, db):
    provider = _create_provider(db, "anthropic")
    body = {
        "provider_name": "local_ollama",
        "message": "hello",
    }

    resp = client.post(f"/chat/{provider.id}", json=body)
    assert resp.status_code == 400
    assert "does not match" in resp.json()["detail"]


def test_chat_unsupported_provider(client, db):
    provider = _create_provider(db, "some_future_provider")
    body = {
        "provider_name": "some_future_provider",
        "message": "hello",
    }

    resp = client.post(f"/chat/{provider.id}", json=body)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "LLM provider not supported"


def test_chat_success_delegates_to_service(client, db, monkeypatch):
    provider = _create_provider(db, "local_ollama")

    def fake_chat_with_provider(db_provider, chat_request):
        assert db_provider.id == provider.id
        assert chat_request.latest_user_message() == "hello"
        return {
            "provider_id": db_provider.id,
            "provider": db_provider.provider,
            "model": "llama3.1",
            "reply": "ok",
        }

    monkeypatch.setattr(chat_router.chat_tool_service.llm_service, "_chat_with_provider", fake_chat_with_provider)

    body = {
        "provider_name": "local_ollama",
        "message": "hello",
        "conversation_id": "conv-1",
        "session_id": "sess-1",
        "request_id": "req-1",
    }
    resp = client.post(f"/chat/{provider.id}", json=body)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["response"]["reply"] == "ok"
    assert payload["response"]["provider"] == "local_ollama"


def test_chat_propagates_provider_http_exception(client, db, monkeypatch):
    provider = _create_provider(db, "local_ollama")

    def fake_chat_with_provider(_db_provider, _chat_request):
        raise HTTPException(status_code=502, detail="downstream failure")

    monkeypatch.setattr(chat_router.chat_tool_service.llm_service, "_chat_with_provider", fake_chat_with_provider)

    body = {
        "provider_name": "local_ollama",
        "message": "hello",
    }
    resp = client.post(f"/chat/{provider.id}", json=body)
    assert resp.status_code == 502
    assert resp.json()["detail"] == "downstream failure"


def test_chat_persists_turn_when_conversation_id_present(client, db, monkeypatch):
    provider = _create_provider(db, "local_ollama")

    def fake_chat_with_provider(_db_provider, _chat_request):
        return {
            "provider": "local_ollama",
            "reply": "assistant-response",
        }

    monkeypatch.setattr(chat_router.chat_tool_service.llm_service, "_chat_with_provider", fake_chat_with_provider)

    body = {
        "provider_name": "local_ollama",
        "conversation_id": "conv-42",
        "message": "hello memory",
    }
    resp = client.post(f"/chat/{provider.id}", json=body)
    assert resp.status_code == 200

    rows = (
        db.query(LLMChatMemory)
        .filter(LLMChatMemory.llm_provider_id == provider.id, LLMChatMemory.conversation_id == "conv-42")
        .order_by(LLMChatMemory.id.asc())
        .all()
    )
    assert len(rows) == 2
    assert rows[0].role == "user"
    assert rows[0].content == "hello memory"
    assert rows[1].role == "assistant"
    assert rows[1].content == "assistant-response"


def test_chat_loads_persisted_memory_into_request(client, db, monkeypatch):
    provider = _create_provider(db, "local_ollama")
    db.add(
        LLMChatMemory(
            llm_provider_id=provider.id,
            conversation_id="conv-99",
            role="user",
            content="old-user-msg",
        )
    )
    db.add(
        LLMChatMemory(
            llm_provider_id=provider.id,
            conversation_id="conv-99",
            role="assistant",
            content="old-assistant-msg",
        )
    )
    db.commit()

    def fake_chat_with_provider(_db_provider, chat_request):
        history = [m.content for m in chat_request.short_term_memory]
        assert "old-user-msg" in history
        assert "old-assistant-msg" in history
        return {
            "provider": "local_ollama",
            "reply": "ok",
        }

    monkeypatch.setattr(chat_router.chat_tool_service.llm_service, "_chat_with_provider", fake_chat_with_provider)

    body = {
        "provider_name": "local_ollama",
        "conversation_id": "conv-99",
        "message": "new-msg",
    }
    resp = client.post(f"/chat/{provider.id}", json=body)
    assert resp.status_code == 200


def test_read_chat_memory_by_conversation(client, db):
    provider = _create_provider(db, "local_ollama")
    db.add(
        LLMChatMemory(
            llm_provider_id=provider.id,
            conversation_id="conv-read",
            role="user",
            content="hello",
        )
    )
    db.add(
        LLMChatMemory(
            llm_provider_id=provider.id,
            conversation_id="conv-read",
            role="assistant",
            content="world",
        )
    )
    db.commit()

    resp = client.get(f"/chat/{provider.id}/memory", params={"conversation_id": "conv-read"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["provider"] == "local_ollama"
    assert payload["memory_count"] == 2
    assert payload["memory"][0]["content"] == "hello"
    assert payload["memory"][1]["content"] == "world"


def test_prune_chat_memory_by_ttl(client, db):
    provider = _create_provider(db, "local_ollama")
    old_ts = datetime.now(timezone.utc) - timedelta(hours=72)

    db.add(
        LLMChatMemory(
            llm_provider_id=provider.id,
            conversation_id="conv-prune",
            role="user",
            content="old-msg",
            created_at=old_ts,
        )
    )
    db.add(
        LLMChatMemory(
            llm_provider_id=provider.id,
            conversation_id="conv-prune",
            role="assistant",
            content="new-msg",
        )
    )
    db.commit()

    resp = client.post("/chat/memory/prune", params={"older_than_hours": 24, "llm_provider_id": provider.id})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["removed_memory_count"] == 1
    assert payload["removed_summary_count"] == 0

    rows = db.query(LLMChatMemory).filter(LLMChatMemory.llm_provider_id == provider.id).all()
    assert len(rows) == 1
    assert rows[0].content == "new-msg"


def test_chat_enforces_max_stored_turns_policy(client, db, monkeypatch):
    provider = _create_provider(db, "local_ollama")
    monkeypatch.setattr(chat_router.chat_memory_service, "LLM_CHAT_MEMORY_MAX_TURNS", 2)

    def fake_chat_with_provider(_db_provider, chat_request):
        return {
            "provider": "local_ollama",
            "reply": f"reply:{chat_request.latest_user_message()}",
        }

    monkeypatch.setattr(chat_router.chat_tool_service.llm_service, "_chat_with_provider", fake_chat_with_provider)

    for idx in range(3):
        resp = client.post(
            f"/chat/{provider.id}",
            json={
                "provider_name": "local_ollama",
                "conversation_id": "conv-window",
                "message": f"m{idx}",
            },
        )
        assert resp.status_code == 200

    rows = (
        db.query(LLMChatMemory)
        .filter(LLMChatMemory.llm_provider_id == provider.id, LLMChatMemory.conversation_id == "conv-window")
        .order_by(LLMChatMemory.id.asc())
        .all()
    )
    assert len(rows) == 4
    assert rows[0].content == "m1"
    assert rows[1].content == "reply:m1"
    assert rows[2].content == "m2"
    assert rows[3].content == "reply:m2"


def test_chat_generates_and_reads_summary(client, db, monkeypatch):
    provider = _create_provider(db, "local_ollama")
    monkeypatch.setattr(chat_router.chat_memory_service, "LLM_CHAT_MEMORY_SUMMARIZATION_TRIGGER_TURNS", 1)

    def fake_chat_with_provider(_db_provider, chat_request):
        prompt = chat_request.latest_user_message()
        if "Summarize this conversation" in prompt:
            return {"provider": "local_ollama", "reply": "summary: user asked about deployment and logs"}
        return {"provider": "local_ollama", "reply": f"reply:{prompt}"}

    monkeypatch.setattr(chat_router.chat_tool_service.llm_service, "_chat_with_provider", fake_chat_with_provider)

    resp = client.post(
        f"/chat/{provider.id}",
        json={
            "provider_name": "local_ollama",
            "conversation_id": "conv-summary",
            "message": "How do I deploy this?",
        },
    )
    assert resp.status_code == 200

    summary_row = (
        db.query(LLMChatSummary)
        .filter(LLMChatSummary.llm_provider_id == provider.id, LLMChatSummary.conversation_id == "conv-summary")
        .first()
    )
    assert summary_row is not None
    assert summary_row.source == "llm"
    assert "deployment and logs" in summary_row.summary_text

    summary_resp = client.get(
        f"/chat/{provider.id}/memory/summary",
        params={"conversation_id": "conv-summary"},
    )
    assert summary_resp.status_code == 200
    summary_payload = summary_resp.json()
    assert summary_payload["summary"]["source"] == "llm"
    assert "deployment and logs" in summary_payload["summary"]["summary_text"]


def test_chat_uses_mcp_tools_when_enabled(client, db, monkeypatch):
    provider = _create_provider(db, "local_ollama")

    def fake_chat_with_provider(_db_provider, chat_request):
        latest = chat_request.latest_user_message()
        if "Return ONLY valid JSON" in latest:
            return {
                "provider": "local_ollama",
                "reply": '{"tools":[{"name":"ping","arguments":{"message":"hello"}}],"reason":"Need live status."}',
            }

        if "MCP_TOOL_RESULTS_JSON=" in (chat_request.system_prompt or ""):
            return {
                "provider": "local_ollama",
                "reply": "Used MCP tool results to answer.",
            }

        return {
            "provider": "local_ollama",
            "reply": "Fallback response.",
        }

    monkeypatch.setattr(chat_router.chat_tool_service.llm_service, "_chat_with_provider", fake_chat_with_provider)

    monkeypatch.setattr(
        chat_router.chat_tool_service.mcp_client_service,
        "list_mcp_tools",
        lambda: MCPToolsListResponse(
            server_url="http://mcp_server:9001/mcp",
            tools=[
                MCPToolInfo(name="ping", description="Ping tool", input_schema={"type": "object"}),
            ],
        ),
    )

    monkeypatch.setattr(
        chat_router.chat_tool_service.mcp_client_service,
        "call_mcp_tool",
        lambda tool_name, arguments: MCPToolInvokeResponse(
            tool_name=tool_name,
            content=[{"type": "text", "text": f"pong: {arguments.get('message', '')}"}],
            is_error=False,
            raw_result={"ok": True},
        ),
    )

    resp = client.post(
        f"/chat/{provider.id}",
        json={
            "provider_name": "local_ollama",
            "message": "Check MCP and help me",
            "metadata": {"enable_mcp_tools": True},
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["response"]["reply"] == "Used MCP tool results to answer."
    assert payload["response"]["mcp_tools"]["enabled"] is True
    assert payload["response"]["mcp_tools"]["used_tool_count"] == 1
    assert payload["response"]["mcp_tools"]["executed_tools"][0]["name"] == "ping"


def test_chat_mcp_tool_blocked_when_required_secret_missing(client, db, monkeypatch):
    from schemas.model import MCPToolRegistry

    provider = _create_provider(db, "local_ollama")
    db.add(
        MCPToolRegistry(
            tool_name="tavily_search",
            description="Search tool",
            enabled=True,
            required_secret_keys=["TAVILY_API_KEY"],
        )
    )
    db.commit()

    def fake_chat_with_provider(_db_provider, chat_request):
        latest = chat_request.latest_user_message()
        if "Return ONLY valid JSON" in latest:
            return {
                "provider": "local_ollama",
                "reply": '{"tools":[{"name":"tavily_search","arguments":{"query":"hello"}}],"reason":"Needs web search."}',
            }
        return {
            "provider": "local_ollama",
            "reply": "Final answer without external tool.",
        }

    monkeypatch.setattr(chat_router.chat_tool_service.llm_service, "_chat_with_provider", fake_chat_with_provider)
    monkeypatch.setattr(
        chat_router.chat_tool_service.mcp_client_service,
        "list_mcp_tools",
        lambda: MCPToolsListResponse(
            server_url="http://mcp_server:9001/mcp",
            tools=[MCPToolInfo(name="tavily_search", description="Search tool", input_schema={"type": "object"})],
        ),
    )

    invoke_called = {"value": False}

    def fake_call_tool(_tool_name, _arguments):
        invoke_called["value"] = True
        return MCPToolInvokeResponse(tool_name="tavily_search", content=[], is_error=False, raw_result={})

    monkeypatch.setattr(chat_router.chat_tool_service.mcp_client_service, "call_mcp_tool", fake_call_tool)

    resp = client.post(
        f"/chat/{provider.id}",
        json={
            "provider_name": "local_ollama",
            "message": "Find latest info",
            "metadata": {"enable_mcp_tools": True},
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert invoke_called["value"] is False
    executed = payload["response"]["mcp_tools"]["executed_tools"]
    assert len(executed) == 1
    assert executed[0]["name"] == "tavily_search"
    assert executed[0]["is_error"] is True
    assert "missing" in executed[0]["error"].lower()
