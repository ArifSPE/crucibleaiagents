import { useState } from "react";
import { EmptyState } from "../components/EmptyState";
import { SectionCard } from "../components/SectionCard";
import { StatusBadge } from "../components/StatusBadge";
import { usePolling } from "../hooks/usePolling";
import { platformApi } from "../services/platformApi";
import type { McpHealthResponse, McpToolsListResponse } from "../types/api";

interface McpServerViewProps {
  health: McpHealthResponse | null;
  toolsPayload: McpToolsListResponse | null;
  loading: boolean;
  error: string | null;
}

function stringifySchema(schema: Record<string, unknown>): string {
  try {
    return JSON.stringify(schema || {}, null, 2);
  } catch {
    return "{}";
  }
}

function McpServerView({ health, toolsPayload, loading, error }: McpServerViewProps) {
  const [expandedSchemas, setExpandedSchemas] = useState<Record<string, boolean>>({});

  function toggleSchema(toolName: string) {
    setExpandedSchemas((prev) => ({
      ...prev,
      [toolName]: !prev[toolName],
    }));
  }

  if (loading) {
    return <div className="page-state">Loading MCP server information...</div>;
  }

  if (error) {
    return <div className="page-state page-state--error">{error}</div>;
  }

  const tools = toolsPayload?.tools || [];

  return (
    <div className="page-grid page-grid--two-column">
      <section className="hero-panel">
        <div>
          <span className="eyebrow">Model Context Protocol</span>
          <h3>MCP server connectivity</h3>
          <p>Validate API to MCP integration and inspect currently registered tool contracts.</p>
        </div>
        <StatusBadge status={health?.status || "unknown"} />
      </section>

      <section className="stats-grid">
        <article className="stat-card">
          <span>Server status</span>
          <strong>{health?.status || "unknown"}</strong>
        </article>
        <article className="stat-card">
          <span>Registered tools</span>
          <strong>{tools.length}</strong>
        </article>
      </section>

      <SectionCard title="MCP server info" subtitle="Live metadata from /mcp/health and /mcp/tools">
        <div className="stack-list">
          <li>
            <div>
              <strong>Server URL</strong>
              <p>{health?.server_url || toolsPayload?.server_url || "Unavailable"}</p>
            </div>
            <div>
              <StatusBadge status={health?.status || "unknown"} />
            </div>
          </li>
          <li>
            <div>
              <strong>Tool count (health)</strong>
              <p>{typeof health?.tool_count === "number" ? String(health.tool_count) : "Unknown"}</p>
            </div>
            <div>
              <span>{tools.length} loaded in tools endpoint</span>
            </div>
          </li>
        </div>
      </SectionCard>

      <div className="mcp-tools-section">
        <SectionCard title="Registered tools" subtitle="Tool metadata and input schema (table view)">
          {tools.length ? (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Description</th>
                    <th>Input schema</th>
                  </tr>
                </thead>
                <tbody>
                  {tools.map((tool) => {
                    const isExpanded = Boolean(expandedSchemas[tool.name]);
                    const schema = stringifySchema(tool.input_schema || {});

                    return (
                      <tr key={tool.name}>
                        <td><strong>{tool.name}</strong></td>
                        <td>{tool.description || "No description"}</td>
                        <td>
                          <div className="mcp-schema-cell">
                            <button
                              type="button"
                              className="button button--small button--ghost"
                              onClick={() => toggleSchema(tool.name)}
                              aria-expanded={isExpanded}
                            >
                              {isExpanded ? "Hide schema" : "Show schema"}
                            </button>
                            {isExpanded ? (
                              <pre className="code-block">{schema}</pre>
                            ) : (
                              <span className="schema-preview">JSON schema hidden</span>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="No MCP tools registered" description="Confirm MCP server startup and tool registration policy variables." />
          )}
        </SectionCard>
      </div>
    </div>
  );
}

export function McpServerPage() {
  const healthState = usePolling(() => platformApi.mcpHealth(), 10000);
  const toolsState = usePolling(() => platformApi.listMcpTools(), 12000);

  return (
    <McpServerView
      health={healthState.data}
      toolsPayload={toolsState.data}
      loading={healthState.loading || toolsState.loading}
      error={healthState.error || toolsState.error}
    />
  );
}
