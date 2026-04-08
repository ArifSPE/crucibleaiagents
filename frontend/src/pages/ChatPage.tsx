import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";
import { usePolling } from "../hooks/usePolling";
import { platformApi } from "../services/platformApi";
import type { ChatMcpToolUsage, LlmModel, LlmProvider } from "../types/api";

interface LocalMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  mcpTools?: ChatMcpToolUsage;
}

const CHAT_DRAFTS_STORAGE_KEY = "chat.draftsByScope.v1";

function newId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function isUserFacingError(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Unexpected error. Please try again.";
}

function prettyJson(value: unknown): string {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return "{}";
  }
}

function loadDraftsFromStorage(): Record<string, string> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(CHAT_DRAFTS_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return {};

    const normalized: Record<string, string> = {};
    for (const [key, value] of Object.entries(parsed)) {
      if (typeof value === "string" && value.trim()) {
        normalized[key] = value;
      }
    }
    return normalized;
  } catch {
    return {};
  }
}

function persistDraftsToStorage(drafts: Record<string, string>) {
  if (typeof window === "undefined") return;
  try {
    if (Object.keys(drafts).length === 0) {
      window.localStorage.removeItem(CHAT_DRAFTS_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(CHAT_DRAFTS_STORAGE_KEY, JSON.stringify(drafts));
  } catch {
    // Ignore storage failures (private mode, quota, etc.) and continue with in-memory drafts.
  }
}

export function ChatPage() {
  const providersState = usePolling(() => platformApi.listProviders(), 15000);
  const providers = providersState.data ?? [];

  const [selectedProviderId, setSelectedProviderId] = useState<number | null>(null);
  const [conversationId, setConversationId] = useState<string>(() => `conv-${newId()}`);
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [draftByScope, setDraftByScope] = useState<Record<string, string>>(() => loadDraftsFromStorage());
  const [submitting, setSubmitting] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [systemPrompt, setSystemPrompt] = useState<string>("");
  const [modelOverride, setModelOverride] = useState<string>("");
  const [temperature, setTemperature] = useState<string>("0.7");
  const [mcpToolsEnabled, setMcpToolsEnabled] = useState<boolean>(false);
  const [modelsState, setModelsState] = useState<{ loading: boolean; error: string | null; models: LlmModel[] }>({
    loading: false,
    error: null,
    models: [],
  });

  const threadRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const selectedProvider = useMemo<LlmProvider | null>(() => {
    if (!providers.length || selectedProviderId === null) return null;
    return providers.find((p) => p.id === selectedProviderId) ?? null;
  }, [providers, selectedProviderId]);

  const activeDraftScopeKey = useMemo<string | null>(() => {
    if (!selectedProvider) return null;
    return `${selectedProvider.id}:${conversationId}`;
  }, [selectedProvider, conversationId]);

  const draft = activeDraftScopeKey ? (draftByScope[activeDraftScopeKey] ?? "") : "";

  function setScopedDraft(nextDraft: string) {
    if (!activeDraftScopeKey) return;
    setDraftByScope((prev) => {
      const trimmed = nextDraft.trim();
      if (!trimmed) {
        if (!(activeDraftScopeKey in prev)) return prev;
        const next = { ...prev };
        delete next[activeDraftScopeKey];
        return next;
      }
      return {
        ...prev,
        [activeDraftScopeKey]: nextDraft,
      };
    });
  }

  function syncInputHeight() {
    const input = inputRef.current;
    if (!input) return;
    const minHeight = parseInt(getComputedStyle(input).lineHeight || "20", 10) * (input.rows || 1);
    input.style.height = `${minHeight}px`;
    input.style.height = `${Math.min(Math.max(input.scrollHeight, minHeight), 180)}px`;
  }

  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [messages, submitting]);

  useEffect(() => {
    persistDraftsToStorage(draftByScope);
  }, [draftByScope]);

  useEffect(() => {
    syncInputHeight();
  }, [draft]);

  useEffect(() => {
    let cancelled = false;
    async function loadModels(providerId: number) {
      setModelsState({ loading: true, error: null, models: [] });
      try {
        const response = await platformApi.getProviderModels(providerId);
        if (cancelled) return;
        setModelsState({ loading: false, error: null, models: response.models ?? [] });
      } catch (error) {
        if (cancelled) return;
        setModelsState({ loading: false, error: isUserFacingError(error), models: [] });
      }
    }

    if (!selectedProvider) {
      setModelsState({ loading: false, error: null, models: [] });
      return;
    }

    void loadModels(selectedProvider.id);
    return () => {
      cancelled = true;
    };
  }, [selectedProvider?.id]);

  useEffect(() => {
    if (selectedProviderId !== null) {
      return;
    }
    if (!providers.length) {
      return;
    }
    setSelectedProviderId(providers[0].id);
  }, [providers, selectedProviderId]);

  function handleNewChat() {
    setConversationId(`conv-${newId()}`);
    setMessages([]);
    setSendError(null);
    inputRef.current?.focus();
  }

  async function handleSend(event: React.FormEvent) {
    event.preventDefault();
    const message = draft.trim();
    const trimmedSystemPrompt = systemPrompt.trim();
    if (!selectedProvider || !message || submitting) return;

    setMessages((prev) => [...prev, { id: newId(), role: "user", content: message }]);
    setScopedDraft("");
    setSendError(null);
    setSubmitting(true);

    try {
      const requestMessages = [
        ...(trimmedSystemPrompt ? [{ role: "system" as const, content: trimmedSystemPrompt }] : []),
        { role: "user" as const, content: message },
      ];

      const envelope = await platformApi.sendChatMessage(selectedProvider.id, {
        provider_name: selectedProvider.provider,
        conversation_id: conversationId,
        session_id: "web-console",
        request_id: `req-${newId()}`,
        messages: requestMessages,
        model: modelOverride.trim() || undefined,
        temperature: temperature ? Number(temperature) : undefined,
        metadata: {
          enable_mcp_tools: mcpToolsEnabled,
        },
      });

      const reply = envelope.response?.reply ?? "";
      if (reply) {
        setMessages((prev) => [
          ...prev,
          {
            id: newId(),
            role: "assistant",
            content: reply,
            mcpTools: envelope.response?.mcp_tools,
          },
        ]);
      }
    } catch (error) {
      setSendError(isUserFacingError(error));
    } finally {
      setSubmitting(false);
    }
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      void handleSend(event as unknown as React.FormEvent);
    }
  }

  return (
    <div className="chat-page">
      <div className="chat-toolbar">
        <div className="chat-toolbar__left">
          {providers.length > 0 ? (
            <select
              aria-label="LLM provider"
              className="chat-provider-select"
              value={selectedProvider?.id ?? ""}
              onChange={(e) => {
                const raw = e.target.value;
                setSelectedProviderId(raw ? Number(raw) : null);
              }}
            >
              <option value="">Select Provider</option>
              {providers.map((p) => (
                <option key={p.id} value={p.id}>{p.provider}</option>
              ))}
            </select>
          ) : (
            <span className="chat-no-provider-hint">
              {providersState.loading ? "Loading providers..." : ""}
              {!providersState.loading && !providers.length ? (
                <>No providers - <Link to="/providers">add one</Link></>
              ) : null}
            </span>
          )}
          {selectedProvider && (
            <code className="chat-conv-chip" title={`Conversation: ${conversationId}`}>
              {conversationId}
            </code>
          )}
        </div>
        <div className="chat-toolbar__center">
          {selectedProvider ? (
            <>
              <select
                aria-label="Model selection"
                className="chat-provider-select"
                value={modelOverride}
                onChange={(e) => setModelOverride(e.target.value)}
                disabled={modelsState.loading}
                title="Select model"
              >
                <option value="">{modelsState.loading ? "Loading models..." : "Provider default"}</option>
                {modelsState.models.map((model) => (
                  <option key={`${model.provider_id}-${model.id}`} value={model.id}>
                    {(model.display_name || model.id)} [{model.provider_id}:{model.provider}]
                  </option>
                ))}
              </select>
            </>
          ) : null}
          <code
            className="chat-conv-chip"
            title={systemPrompt.trim() ? `System prompt: ${systemPrompt.trim()}` : "System prompt not set"}
          >
            {systemPrompt.trim() ? `System: ${systemPrompt.trim()}` : "System: not set"}
          </code>
        </div>
        <div className="chat-toolbar__right">
          <button
            className={`button button--small ${mcpToolsEnabled ? "button--active" : "button--ghost"}`}
            onClick={() => setMcpToolsEnabled((v) => !v)}
            type="button"
            title="Toggle MCP-backed tool orchestration for chat responses"
            aria-pressed={mcpToolsEnabled}
          >
            {mcpToolsEnabled ? "MCP: On" : "MCP: Off"}
          </button>
          <button
            className={`button button--ghost button--small${settingsOpen ? " button--active" : ""}`}
            onClick={() => setSettingsOpen((v) => !v)}
            type="button"
            aria-expanded={settingsOpen}
          >
            Settings
          </button>
          <button className="button button--ghost button--small" onClick={handleNewChat} type="button">
            New chat
          </button>
          <Link className="button button--ghost button--small" to="/chat-memory">
            Memory &amp; History
          </Link>
        </div>
      </div>

      <div className="chat-system-banner">
        <label className="chat-system-banner__field">
          <strong>System Prompt</strong>
          <textarea
            rows={2}
            placeholder="Optional instructions sent before user message"
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
          />
          <small className="chat-system-banner__meta">
            MCP-backed tools are currently <strong>{mcpToolsEnabled ? "enabled" : "disabled"}</strong> for this chat.
          </small>
        </label>
      </div>

      {settingsOpen && (
        <div className="chat-settings">
          <div className="chat-settings__row">
            <label className="chat-settings__field">
              <span>Model override</span>
              <select
                value={modelOverride}
                onChange={(e) => setModelOverride(e.target.value)}
                disabled={!selectedProvider || modelsState.loading}
              >
                <option value="">Provider default</option>
                {modelsState.models.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.display_name || model.id}
                  </option>
                ))}
              </select>
              {modelsState.error ? <small className="inline-feedback inline-feedback--error">{modelsState.error}</small> : null}
            </label>
            <label className="chat-settings__field">
              <span>Temperature</span>
              <input
                inputMode="decimal"
                placeholder="0.7"
                value={temperature}
                onChange={(e) => setTemperature(e.target.value)}
              />
            </label>
            <label className="chat-settings__field chat-settings__field--toggle">
              <span>MCP tools</span>
              <label className="chat-toggle">
                <input
                  type="checkbox"
                  checked={mcpToolsEnabled}
                  onChange={(e) => setMcpToolsEnabled(e.target.checked)}
                />
                <span>Allow MCP-assisted tool use during chat</span>
              </label>
            </label>
          </div>
        </div>
      )}

      <div className="chat-thread" ref={threadRef}>
        {messages.length === 0 && !submitting ? (
          <EmptyState
            title={selectedProvider ? `Chat with ${selectedProvider.provider}` : "Select a provider"}
            description={
              selectedProvider
                ? "Type a message below. Conversations are persisted and auto-summarized as they grow."
                : "Choose an LLM provider in the toolbar above to begin."
            }
          />
        ) : null}
        {messages.map((msg) => (
          <div key={msg.id} className={`chat-bubble chat-bubble--${msg.role}`}>
            <p>{msg.content}</p>
            {msg.role === "assistant" && msg.mcpTools?.enabled ? (
              <div className="chat-mcp-meta">
                <strong>MCP tools:</strong> {msg.mcpTools.used_tool_count} used
                {msg.mcpTools.executed_tools.length ? (
                  <span> ({msg.mcpTools.executed_tools.map((tool) => tool.name).join(", ")})</span>
                ) : (
                  <span> (none)</span>
                )}

                <details className="chat-mcp-details">
                  <summary>View MCP execution details</summary>
                  {msg.mcpTools.planning_reason ? (
                    <p className="chat-mcp-details__reason">
                      <strong>Planner reason:</strong> {msg.mcpTools.planning_reason}
                    </p>
                  ) : null}
                  {msg.mcpTools.executed_tools.length ? (
                    <div className="chat-mcp-details__list">
                      {msg.mcpTools.executed_tools.map((tool, index) => (
                        <article key={`${msg.id}-${tool.name}-${index}`} className="chat-mcp-tool-card">
                          <header>
                            <strong>{tool.name}</strong>
                            <span>{tool.is_error ? "error" : "ok"}</span>
                          </header>
                          <pre className="code-block">{prettyJson(tool.arguments || {})}</pre>
                          {tool.error ? <p className="inline-feedback inline-feedback--error">{tool.error}</p> : null}
                          {tool.content !== undefined ? (
                            <pre className="code-block">{prettyJson(tool.content)}</pre>
                          ) : null}
                        </article>
                      ))}
                    </div>
                  ) : (
                    <p className="chat-mcp-details__empty">No tools executed for this response.</p>
                  )}
                </details>
              </div>
            ) : null}
          </div>
        ))}
        {submitting && (
          <div className="chat-bubble chat-bubble--assistant chat-bubble--thinking">
            <span className="chat-thinking-dots">
              <span />
              <span />
              <span />
            </span>
          </div>
        )}
      </div>

      {sendError ? (
        <p className="chat-send-error inline-feedback inline-feedback--error" role="alert">
          {sendError}
        </p>
      ) : null}

      <form className="chat-input-bar" onSubmit={handleSend}>
        <textarea
          ref={inputRef}
          aria-label="Message"
          className="chat-input"
          placeholder={
            selectedProvider
              ? `Message ${selectedProvider.provider}... (Ctrl+Enter to send)`
              : "Select a provider first"
          }
          rows={4}
          value={draft}
          onChange={(e) => {
            setScopedDraft(e.target.value);
            if (sendError) setSendError(null);
          }}
          onKeyDown={handleKeyDown}
          disabled={!selectedProvider || submitting}
        />
        <button
          className="button button--primary"
          type="submit"
          disabled={!selectedProvider || !draft.trim() || submitting}
        >
          {submitting ? "..." : "Send"}
        </button>
      </form>
    </div>
  );
}
