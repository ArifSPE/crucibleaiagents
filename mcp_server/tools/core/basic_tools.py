from __future__ import annotations

from typing import TypedDict

from fastmcp import FastMCP
from langchain_core.prompts import PromptTemplate
from langgraph.graph import END, StateGraph

from mcp_server.tool_registry import MCPToolSpec


class TextAnalysisState(TypedDict):
    text: str
    normalized_text: str
    tokens: list[str]
    word_count: int


def _normalize_text(state: TextAnalysisState) -> dict:
    raw = (state.get("text") or "").strip()
    normalized = " ".join(raw.split())
    return {"normalized_text": normalized}


def _tokenize_text(state: TextAnalysisState) -> dict:
    normalized = state.get("normalized_text") or ""
    tokens = [part for part in normalized.split(" ") if part]
    return {"tokens": tokens}


def _count_words(state: TextAnalysisState) -> dict:
    tokens = state.get("tokens") or []
    return {"word_count": len(tokens)}


_graph_builder = StateGraph(TextAnalysisState)
_graph_builder.add_node("normalize", _normalize_text)
_graph_builder.add_node("tokenize", _tokenize_text)
_graph_builder.add_node("count", _count_words)
_graph_builder.set_entry_point("normalize")
_graph_builder.add_edge("normalize", "tokenize")
_graph_builder.add_edge("tokenize", "count")
_graph_builder.add_edge("count", END)
_TEXT_ANALYSIS_GRAPH = _graph_builder.compile()


def _register_ping_tool(mcp: FastMCP) -> None:
    @mcp.tool
    def ping(message: str = "hello") -> str:
        """Lightweight connectivity check tool."""
        return f"pong: {message}"


def _register_analyze_text_tool(mcp: FastMCP) -> None:
    @mcp.tool
    def analyze_text(text: str) -> dict:
        """Analyze text using LangGraph and LangChain prompt templating."""
        state = _TEXT_ANALYSIS_GRAPH.invoke(
            {
                "text": text,
                "normalized_text": "",
                "tokens": [],
                "word_count": 0,
            }
        )

        prompt = PromptTemplate.from_template(
            "Provide a concise technical summary for the following text:\n\n{text}"
        ).format(text=(state.get("normalized_text") or "")[:500])

        return {
            "normalized_text": state.get("normalized_text") or "",
            "word_count": state.get("word_count") or 0,
            "prompt_preview": prompt,
        }


TOOL_SPECS = [
    MCPToolSpec(
        name="ping",
        description="Lightweight connectivity check tool",
        register=_register_ping_tool,
        version="1.0.0",
        tags=("core", "health"),
        risk_level="low",
    ),
    MCPToolSpec(
        name="analyze_text",
        description="Analyze text using LangGraph workflow",
        register=_register_analyze_text_tool,
        version="1.0.0",
        tags=("core", "analysis", "langgraph", "langchain"),
        risk_level="low",
    ),
]
