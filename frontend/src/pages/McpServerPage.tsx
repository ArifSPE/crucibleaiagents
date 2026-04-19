import { useMemo, useState } from "react";
import { EmptyState } from "../components/EmptyState";
import { SectionCard } from "../components/SectionCard";
import { StatusBadge } from "../components/StatusBadge";
import { usePolling } from "../hooks/usePolling";
import { platformApi } from "../services/platformApi";
import type {
  McpHealthResponse,
  McpPromptsListResponse,
  McpResourcesListResponse,
  McpToolsListResponse,
} from "../types/api";

interface McpServerViewProps {
  health: McpHealthResponse | null;
  toolsPayload: McpToolsListResponse | null;
  resourcesPayload: McpResourcesListResponse | null;
  promptsPayload: McpPromptsListResponse | null;
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

function McpServerView({ health, toolsPayload, resourcesPayload, promptsPayload, loading, error }: McpServerViewProps) {
  const [expandedSchemas, setExpandedSchemas] = useState<Record<string, boolean>>({});
  const [resourcePreview, setResourcePreview] = useState<string>("");
  const [resourcePreviewUri, setResourcePreviewUri] = useState<string>("");
  const [resourceError, setResourceError] = useState<string | null>(null);
  const [resourceLoading, setResourceLoading] = useState(false);
  const [promptResult, setPromptResult] = useState<string>("");
  const [promptError, setPromptError] = useState<string | null>(null);
  const [promptLoading, setPromptLoading] = useState(false);
  const [promptArgumentsText, setPromptArgumentsText] = useState('{"filepath":"README.md"}');

  function toggleSchema(toolName: string) {
    setExpandedSchemas((prev) => ({
      ...prev,
      [toolName]: !prev[toolName],
    }));
  }

  const tools = toolsPayload?.tools || [];
  const resources = resourcesPayload?.resources || [];
  const prompts = promptsPayload?.prompts || [];

  const defaultPromptName = useMemo(() => prompts[0]?.name || "", [prompts]);
  const [selectedPromptName, setSelectedPromptName] = useState("");
  const activePromptName = selectedPromptName || defaultPromptName;

  async function handleResourcePreview(uri: string) {
    setResourceLoading(true);
    setResourceError(null);
    try {
      const response = await platformApi.readMcpResource(uri);
      const contents = Array.isArray(response.contents) ? response.contents : [];
      const joined = contents
        .map((item) => {
          const candidate = item as { text?: unknown; mimeType?: unknown; mime_type?: unknown };
          return typeof candidate.text === "string"
            ? candidate.text
            : JSON.stringify(item, null, 2);
        })
        .join("\n\n");
      setResourcePreview(joined || "No previewable content returned.");
      setResourcePreviewUri(uri);
    } catch (previewError) {
      setResourceError(previewError instanceof Error ? previewError.message : "Unable to load resource preview.");
      setResourcePreview("");
      setResourcePreviewUri(uri);
    } finally {
      setResourceLoading(false);
    }
  }

  async function handlePromptRender() {
    if (!activePromptName) {
      setPromptError("No prompt is available to render.");
      return;
    }

    setPromptLoading(true);
    setPromptError(null);
    try {
      const parsedArguments = promptArgumentsText.trim() ? JSON.parse(promptArgumentsText) : {};
      const response = await platformApi.renderMcpPrompt(activePromptName, parsedArguments);
      const messages = Array.isArray(response.messages) ? response.messages : [];
      const rendered = messages
        .map((message) => {
          const candidate = message as { role?: unknown; content?: unknown };
          const role = typeof candidate.role === "string" ? candidate.role : "message";
          const content = candidate.content;
          if (typeof content === "string") {
            return `${role}: ${content}`;
          }
          if (content && typeof content === "object" && "text" in (content as Record<string, unknown>)) {
            const text = (content as Record<string, unknown>).text;
            return `${role}: ${typeof text === "string" ? text : JSON.stringify(content, null, 2)}`;
          }
          return `${role}: ${JSON.stringify(message, null, 2)}`;
        })
        .join("\n\n");
      setPromptResult(rendered || "No prompt messages returned.");
    } catch (renderError) {
      if (renderError instanceof SyntaxError) {
        setPromptError("Arguments must be valid JSON.");
      } else {
        setPromptError(renderError instanceof Error ? renderError.message : "Unable to render prompt.");
      }
      setPromptResult("");
    } finally {
      setPromptLoading(false);
    }
  }

  if (loading) {
    return <div className="page-state">Loading MCP server information...</div>;
  }

  if (error) {
    return <div className="page-state page-state--error">{error}</div>;
  }

  return (
    <div className="page-grid page-grid--two-column">
      <section className="hero-panel">
        <div>
          <span className="eyebrow">Model Context Protocol</span>
          <h3>MCP server connectivity</h3>
          <p>Inspect tools, preview resources, and render prompt templates directly from the operator console.</p>
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
        <article className="stat-card">
          <span>Resources</span>
          <strong>{typeof health?.resource_count === "number" ? health.resource_count : resources.length}</strong>
        </article>
        <article className="stat-card">
          <span>Prompts</span>
          <strong>{typeof health?.prompt_count === "number" ? health.prompt_count : prompts.length}</strong>
        </article>
      </section>

      <SectionCard title="MCP server info" subtitle="Live metadata from the health, tools, resources, and prompts endpoints">
        <div className="stack-list">
          <li>
            <div>
              <strong>Server URL</strong>
              <p>{health?.server_url || toolsPayload?.server_url || resourcesPayload?.server_url || promptsPayload?.server_url || "Unavailable"}</p>
            </div>
            <div>
              <StatusBadge status={health?.status || "unknown"} />
            </div>
          </li>
          <li>
            <div>
              <strong>Capability summary</strong>
              <p>{tools.length} tools, {resources.length} resources, {prompts.length} prompts</p>
            </div>
            <div>
              <span>Live MCP inventory</span>
            </div>
          </li>
        </div>
      </SectionCard>

      <div className="mcp-tools-section">
        <SectionCard title="Registered tools" subtitle="Tool metadata and input schema">
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

      <SectionCard title="Registered resources" subtitle="Preview file-backed MCP resources from the mounted safe roots">
        {resources.length ? (
          <div className="mcp-resource-layout">
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>URI</th>
                    <th>Type</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {resources.map((resource) => (
                    <tr key={resource.uri}>
                      <td>
                        <strong>{resource.name || resource.uri}</strong>
                        <div className="schema-preview">{resource.description || "No description"}</div>
                      </td>
                      <td>{resource.uri}</td>
                      <td>{resource.mime_type || "unknown"}</td>
                      <td>
                        <button
                          type="button"
                          className="button button--small button--ghost"
                          onClick={() => handleResourcePreview(resource.uri)}
                          disabled={resourceLoading}
                        >
                          Preview
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mcp-preview-panel">
              <strong>Resource preview</strong>
              <p className="schema-preview">{resourcePreviewUri || "Select a resource to preview its content."}</p>
              {resourceError ? <div className="page-state page-state--error">{resourceError}</div> : null}
              <pre className="code-block">{resourceLoading ? "Loading resource preview..." : resourcePreview || "No resource selected."}</pre>
            </div>
          </div>
        ) : (
          <EmptyState title="No MCP resources found" description="Mounted resource roots will appear here when the MCP server exposes them." />
        )}
      </SectionCard>

      <SectionCard title="Prompt templates" subtitle="Render prompt payloads for summarization and review workflows">
        {prompts.length ? (
          <div className="mcp-prompt-layout">
            <div className="stack-list">
              {prompts.map((prompt) => (
                <li key={prompt.name} className="mcp-prompt-row">
                  <div>
                    <strong>{prompt.name}</strong>
                    <p>{prompt.description || "No description"}</p>
                    <span className="schema-preview">
                      Args: {prompt.arguments?.length ? prompt.arguments.map((arg) => `${arg.name}${arg.required ? "*" : ""}`).join(", ") : "none"}
                    </span>
                  </div>
                  <div>
                    <button
                      type="button"
                      className={`button button--small ${activePromptName === prompt.name ? "button--active" : "button--ghost"}`}
                      onClick={() => setSelectedPromptName(prompt.name)}
                    >
                      Select
                    </button>
                  </div>
                </li>
              ))}
            </div>

            <div className="mcp-preview-panel">
              <label className="form-field">
                <span>Selected prompt</span>
                <input value={activePromptName} readOnly />
              </label>
              <label className="form-field">
                <span>Arguments JSON</span>
                <textarea
                  rows={5}
                  value={promptArgumentsText}
                  onChange={(event) => setPromptArgumentsText(event.target.value)}
                />
              </label>
              <button type="button" className="button button--primary" onClick={handlePromptRender} disabled={promptLoading || !activePromptName}>
                Render prompt
              </button>
              {promptError ? <div className="page-state page-state--error">{promptError}</div> : null}
              <pre className="code-block">{promptLoading ? "Rendering prompt..." : promptResult || "Render a prompt to preview its messages."}</pre>
            </div>
          </div>
        ) : (
          <EmptyState title="No prompt templates found" description="Prompt templates exposed by the MCP server will be shown here." />
        )}
      </SectionCard>
    </div>
  );
}

export function McpServerPage() {
  const healthState = usePolling(() => platformApi.mcpHealth(), 10000);
  const toolsState = usePolling(() => platformApi.listMcpTools(), 12000);
  const resourcesState = usePolling(() => platformApi.listMcpResources(), 15000);
  const promptsState = usePolling(() => platformApi.listMcpPrompts(), 15000);

  return (
    <McpServerView
      health={healthState.data}
      toolsPayload={toolsState.data}
      resourcesPayload={resourcesState.data}
      promptsPayload={promptsState.data}
      loading={healthState.loading || toolsState.loading || resourcesState.loading || promptsState.loading}
      error={healthState.error || toolsState.error || resourcesState.error || promptsState.error}
    />
  );
}
