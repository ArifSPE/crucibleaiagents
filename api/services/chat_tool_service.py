from __future__ import annotations

import json
import re
from typing import Any

from schemas.llm_providers import LLMProviderChatRequest
from schemas.model import LlmProvider
from services import llm_service, mcp_client_service
from utils.config import (
    MCP_CHAT_TOOLING_ENABLED,
    MCP_CHAT_TOOLING_MAX_TOOLS,
    MCP_CHAT_TOOLING_MAX_RESULT_CHARS,
)
from utils.logger import get_logger, log_event, log_exception


LOGGER = get_logger("api.services.chat_tool_service")


def _bool_from_metadata(metadata: dict[str, Any] | None, key: str, default: bool) -> bool:
    if not isinstance(metadata, dict) or key not in metadata:
        return default
    raw = metadata.get(key)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _extract_json_payload(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if not cleaned:
        return {}

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    fenced_match = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", cleaned, flags=re.IGNORECASE)
    if fenced_match:
        try:
            parsed = json.loads(fenced_match.group(1))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}

    return {}


def _summarize_tools_for_prompt(tools: list[Any]) -> str:
    summarized: list[str] = []
    for item in tools[:20]:
        name = getattr(item, "name", "") if not isinstance(item, dict) else str(item.get("name", ""))
        description = getattr(item, "description", "") if not isinstance(item, dict) else str(item.get("description", ""))
        input_schema = getattr(item, "input_schema", {}) if not isinstance(item, dict) else item.get("input_schema", {})
        schema_text = json.dumps(input_schema or {}, ensure_ascii=True)
        summarized.append(f"- {name}: {description} | input_schema={schema_text[:700]}")
    return "\n".join(summarized)


def _build_tool_plan_prompt(user_message: str, tools: list[Any]) -> str:
    tool_lines = _summarize_tools_for_prompt(tools)
    return (
        "You are a tool planning assistant. "
        "Given the user request and available MCP tools, decide what tools (if any) should be called before final answering.\n\n"
        "Return ONLY valid JSON in this exact shape:\n"
        '{"tools":[{"name":"tool_name","arguments":{}}],"reason":"short reason"}\n\n'
        "Rules:\n"
        "- Choose at most 3 tools.\n"
        "- Use only names from the provided list.\n"
        "- If no tool is needed, return {\"tools\":[],\"reason\":\"...\"}.\n"
        "- Arguments must be a JSON object.\n\n"
        f"User request:\n{user_message}\n\n"
        f"Available tools:\n{tool_lines}\n"
    )


def _plan_tools_with_llm(
    provider: LlmProvider,
    request_body: LLMProviderChatRequest,
    user_message: str,
    available_tools: list[Any],
) -> tuple[list[dict[str, Any]], str]:
    plan_prompt = _build_tool_plan_prompt(user_message, available_tools)
    planner_request = LLMProviderChatRequest(
        provider_name=request_body.provider_name,
        message=plan_prompt,
        model=request_body.model,
        temperature=0.0,
        max_tokens=min(request_body.max_tokens or 512, 1024),
        metadata={"mcp_plan_only": True},
    )

    planner_response = llm_service._chat_with_provider(provider, planner_request)
    plan_text = str(planner_response.get("reply", "") or "")
    payload = _extract_json_payload(plan_text)

    raw_tools = payload.get("tools", []) if isinstance(payload, dict) else []
    reason = str(payload.get("reason", "") or "") if isinstance(payload, dict) else ""
    if not isinstance(raw_tools, list):
        return [], reason

    available_names = {
        (getattr(tool, "name", "") if not isinstance(tool, dict) else str(tool.get("name", ""))).strip()
        for tool in available_tools
    }

    planned_tools: list[dict[str, Any]] = []
    for item in raw_tools:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        arguments = item.get("arguments")
        if not name or name not in available_names:
            continue
        if not isinstance(arguments, dict):
            arguments = {}
        planned_tools.append({"name": name, "arguments": arguments})
        if len(planned_tools) >= max(1, MCP_CHAT_TOOLING_MAX_TOOLS):
            break

    return planned_tools, reason


def _append_tool_context_to_prompt(base_prompt: str | None, tool_results: list[dict[str, Any]]) -> str:
    tool_results_json = json.dumps(tool_results, ensure_ascii=True)[: max(500, MCP_CHAT_TOOLING_MAX_RESULT_CHARS)]
    tool_instructions = (
        "Use the following MCP tool results as trusted runtime context. "
        "If tool data is insufficient, say what additional data is needed.\n"
        f"MCP_TOOL_RESULTS_JSON={tool_results_json}"
    )

    if base_prompt and base_prompt.strip():
        return f"{base_prompt.strip()}\n\n{tool_instructions}"
    return tool_instructions


def chat_with_optional_mcp_tools(provider: LlmProvider, request_body: LLMProviderChatRequest) -> dict[str, Any]:
    use_tools = _bool_from_metadata(request_body.metadata, "enable_mcp_tools", MCP_CHAT_TOOLING_ENABLED)
    user_message = request_body.latest_user_message()

    if not use_tools or not user_message:
        return llm_service._chat_with_provider(provider, request_body)

    try:
        tools_payload = mcp_client_service.list_mcp_tools()
    except Exception as exc:
        log_event(
            LOGGER,
            30,
            "chat.mcp.tools.unavailable",
            "MCP tools unavailable; falling back to direct LLM chat",
            provider_id=provider.id,
            provider=provider.provider,
            error=str(exc),
        )
        return llm_service._chat_with_provider(provider, request_body)

    available_tools = list(tools_payload.tools or [])
    if not available_tools:
        return llm_service._chat_with_provider(provider, request_body)

    try:
        planned_tools, planning_reason = _plan_tools_with_llm(provider, request_body, user_message, available_tools)
    except Exception as exc:
        log_exception(
            LOGGER,
            "chat.mcp.plan.failed",
            "Failed while planning MCP tool usage; falling back to direct LLM chat",
            provider_id=provider.id,
            provider=provider.provider,
            error=str(exc),
        )
        return llm_service._chat_with_provider(provider, request_body)

    if not planned_tools:
        response = llm_service._chat_with_provider(provider, request_body)
        response["mcp_tools"] = {
            "enabled": True,
            "planned_tools": [],
            "executed_tools": [],
            "planning_reason": planning_reason,
            "used_tool_count": 0,
        }
        return response

    executed_tools: list[dict[str, Any]] = []
    for planned in planned_tools:
        tool_name = str(planned.get("name") or "")
        arguments = planned.get("arguments") if isinstance(planned.get("arguments"), dict) else {}
        try:
            result = mcp_client_service.call_mcp_tool(tool_name, arguments)
            executed_tools.append(
                {
                    "name": tool_name,
                    "arguments": arguments,
                    "is_error": bool(result.is_error),
                    "content": result.content,
                }
            )
        except Exception as exc:
            executed_tools.append(
                {
                    "name": tool_name,
                    "arguments": arguments,
                    "is_error": True,
                    "error": str(exc),
                }
            )

    enriched_request = request_body.model_copy(
        update={
            "system_prompt": _append_tool_context_to_prompt(request_body.system_prompt, executed_tools),
        }
    )
    final_response = llm_service._chat_with_provider(provider, enriched_request)
    final_response["mcp_tools"] = {
        "enabled": True,
        "planned_tools": planned_tools,
        "executed_tools": executed_tools,
        "planning_reason": planning_reason,
        "used_tool_count": len(executed_tools),
    }

    log_event(
        LOGGER,
        20,
        "chat.mcp.orchestration.completed",
        "Completed MCP-assisted chat orchestration",
        provider_id=provider.id,
        provider=provider.provider,
        planned_tool_count=len(planned_tools),
        executed_tool_count=len(executed_tools),
    )

    return final_response