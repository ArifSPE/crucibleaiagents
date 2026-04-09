from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

import httpx
from fastmcp import FastMCP

from mcp_server.secret_resolver import resolve_tool_secret
from mcp_server.tool_registry import MCPToolSpec


def _safe_timeout_seconds() -> int:
    raw = (os.getenv("MCP_WEB_REQUEST_TIMEOUT_SECONDS", "10") or "10").strip()
    try:
        return max(1, min(60, int(raw)))
    except ValueError:
        return 10


def _allowed_hosts() -> set[str]:
    raw = (os.getenv("MCP_ALLOWED_WEB_HOSTS", "") or "").strip()
    if not raw:
        return set()
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def _validate_target_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http and https URLs are allowed")

    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("Target URL must include a valid host")

    allowlist = _allowed_hosts()
    if allowlist and host not in allowlist:
        raise ValueError(f"Host '{host}' is not in MCP_ALLOWED_WEB_HOSTS")

    return parsed.geturl()


def _register_tavily_search_tool(mcp: FastMCP) -> None:
    @mcp.tool
    def tavily_search(query: str, max_results: int = 5) -> dict[str, Any]:
        """Search the web using Tavily API."""
        api_key = resolve_tool_secret("tavily_search", "TAVILY_API_KEY") or (os.getenv("TAVILY_API_KEY", "") or "").strip()
        if not api_key:
            return {
                "status": "error",
                "error": "TAVILY_API_KEY is not configured",
                "results": [],
            }

        trimmed_query = (query or "").strip()
        if not trimmed_query:
            return {
                "status": "error",
                "error": "query is required",
                "results": [],
            }

        timeout_seconds = _safe_timeout_seconds()
        limit = max(1, min(10, int(max_results)))

        payload = {
            "api_key": api_key,
            "query": trimmed_query,
            "max_results": limit,
            "search_depth": "basic",
        }

        try:
            with httpx.Client(timeout=timeout_seconds) as client:
                response = client.post("https://api.tavily.com/search", json=payload)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            return {
                "status": "error",
                "error": f"Tavily request failed: {exc}",
                "results": [],
            }

        results = data.get("results") if isinstance(data, dict) else []
        normalized_results = []
        if isinstance(results, list):
            for item in results[:limit]:
                if not isinstance(item, dict):
                    continue
                normalized_results.append(
                    {
                        "title": item.get("title"),
                        "url": item.get("url"),
                        "content": item.get("content"),
                        "score": item.get("score"),
                    }
                )

        return {
            "status": "ok",
            "query": trimmed_query,
            "result_count": len(normalized_results),
            "results": normalized_results,
        }


def _register_web_service_call_tool(mcp: FastMCP) -> None:
    @mcp.tool
    def web_service_call(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
        """Call an HTTP GET endpoint with optional headers and safe host allowlist enforcement."""
        try:
            target = _validate_target_url(url)
        except ValueError as exc:
            return {
                "status": "error",
                "error": str(exc),
                "url": url,
            }

        timeout_seconds = _safe_timeout_seconds()

        safe_headers: dict[str, str] = {}
        if headers:
            for key, value in headers.items():
                k = str(key or "").strip()
                if not k:
                    continue
                # Do not forward authorization or cookie-like headers from tool callers.
                if k.lower() in {"authorization", "cookie", "set-cookie", "proxy-authorization"}:
                    continue
                safe_headers[k] = str(value or "")

        try:
            with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
                response = client.get(target, headers=safe_headers)
            content_type = response.headers.get("content-type", "")
            body_preview = response.text[:2000]
        except Exception as exc:
            return {
                "status": "error",
                "error": f"Web service call failed: {exc}",
                "url": target,
            }

        return {
            "status": "ok",
            "url": target,
            "status_code": response.status_code,
            "content_type": content_type,
            "headers": {k: v for k, v in response.headers.items() if k.lower() in {"content-type", "cache-control", "date"}},
            "body_preview": body_preview,
        }


TOOL_SPECS = [
    MCPToolSpec(
        name="tavily_search",
        description="Search the web using Tavily",
        register=_register_tavily_search_tool,
        version="1.0.0",
        tags=("integration", "search", "sample"),
        risk_level="medium",
    ),
    MCPToolSpec(
        name="web_service_call",
        description="Call external HTTP GET services with allowlist protection",
        register=_register_web_service_call_tool,
        version="1.0.0",
        tags=("integration", "http", "sample"),
        risk_level="medium",
    ),
]
