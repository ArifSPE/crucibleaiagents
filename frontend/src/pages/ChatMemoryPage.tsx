import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";
import { SectionCard } from "../components/SectionCard";
import { usePolling } from "../hooks/usePolling";
import { platformApi } from "../services/platformApi";
import type { ChatMemoryItem, LlmProvider } from "../types/api";

function formatTimestamp(value: string | null): string {
  if (!value) return "—";
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function isUserFacingError(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Unexpected error.";
}

interface Feedback {
  text: string;
  tone: "success" | "error";
}

export function ChatMemoryPage() {
  const providersState = usePolling(() => platformApi.listProviders(), 30000);
  const providers = providersState.data ?? [];

  const [selectedProviderId, setSelectedProviderId] = useState<number | null>(null);
  const [conversationId, setConversationId] = useState<string>("");
  const [sessionId, setSessionId] = useState<string>("web-console");
  const [pruneHours, setPruneHours] = useState<string>("168");

  const [refreshing, setRefreshing] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [pruning, setPruning] = useState(false);
  const [summaryFeedback, setSummaryFeedback] = useState<Feedback | null>(null);
  const [memoryFeedback, setMemoryFeedback] = useState<Feedback | null>(null);

  const selectedProvider = useMemo<LlmProvider | null>(() => {
    if (!providers.length) return null;
    if (selectedProviderId !== null) {
      return providers.find((p) => p.id === selectedProviderId) ?? null;
    }
    return providers[0] ?? null;
  }, [providers, selectedProviderId]);

  const effectiveProviderId = selectedProvider?.id ?? null;
  const scopeReady = Boolean(effectiveProviderId && (conversationId.trim() || sessionId.trim()));

  const memoryState = usePolling(
    () => {
      if (!effectiveProviderId || !(conversationId.trim() || sessionId.trim())) {
        return Promise.resolve(null);
      }
      return platformApi.getChatMemory(effectiveProviderId, {
        conversationId: conversationId.trim() || undefined,
        sessionId: sessionId.trim() || undefined,
        limit: 200,
      });
    },
    10000,
    [effectiveProviderId, conversationId, sessionId],
  );

  const summaryState = usePolling(
    () => {
      if (!effectiveProviderId || !(conversationId.trim() || sessionId.trim())) {
        return Promise.resolve(null);
      }
      return platformApi.getChatMemorySummary(effectiveProviderId, {
        conversationId: conversationId.trim() || undefined,
        sessionId: sessionId.trim() || undefined,
      });
    },
    15000,
    [effectiveProviderId, conversationId, sessionId],
  );

  const transcript = memoryState.data?.memory ?? [];

  async function handleRefresh() {
    setRefreshing(true);
    setSummaryFeedback(null);
    try {
      await Promise.all([memoryState.refresh(), summaryState.refresh()]);
      setSummaryFeedback({ text: "Memory and summary refreshed.", tone: "success" });
    } catch (error) {
      setSummaryFeedback({ text: isUserFacingError(error), tone: "error" });
    } finally {
      setRefreshing(false);
    }
  }

  async function handleRegenerate() {
    if (!effectiveProviderId) return;
    setRegenerating(true);
    setSummaryFeedback(null);
    try {
      await platformApi.regenerateChatSummary(effectiveProviderId, {
        conversationId: conversationId.trim() || undefined,
        sessionId: sessionId.trim() || undefined,
      });
      await summaryState.refresh();
      setSummaryFeedback({ text: "Summary regenerated from current conversation history.", tone: "success" });
    } catch (error) {
      setSummaryFeedback({ text: isUserFacingError(error), tone: "error" });
    } finally {
      setRegenerating(false);
    }
  }

  async function handlePrune() {
    if (!effectiveProviderId) return;
    const hours = Number(pruneHours);
    if (!Number.isInteger(hours) || hours < 1) {
      setMemoryFeedback({ text: "Enter a whole number of hours greater than zero.", tone: "error" });
      return;
    }
    setPruning(true);
    setMemoryFeedback(null);
    try {
      const result = await platformApi.pruneChatMemory({ providerId: effectiveProviderId, olderThanHours: hours });
      await Promise.all([memoryState.refresh(), summaryState.refresh()]);
      setMemoryFeedback({
        text: `Removed ${result.removed_memory_count} messages and ${result.removed_summary_count} summaries older than ${hours}h.`,
        tone: "success",
      });
    } catch (error) {
      setMemoryFeedback({ text: isUserFacingError(error), tone: "error" });
    } finally {
      setPruning(false);
    }
  }

  return (
    <div className="page-grid">
      <div className="memory-page-header">
        <div>
          <p className="eyebrow">Chat Memory</p>
          <h2 className="memory-page-title">History &amp; Memory Management</h2>
          <p className="memory-page-subtitle">
            Inspect persisted conversation history, summaries, and manage retention policies.
          </p>
        </div>
        <Link className="button button--ghost button--small" to="/chat">
          ← Back to chat
        </Link>
      </div>

      <SectionCard title="Scope" subtitle="Select a provider and scope to inspect stored memory">
        <div className="form-grid">
          <label>
            <span>Provider</span>
            <select
              value={selectedProvider?.id ?? ""}
              onChange={(e) => setSelectedProviderId(Number(e.target.value))}
              disabled={!providers.length}
            >
              {providers.map((p) => (
                <option key={p.id} value={p.id}>{p.provider}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Session ID</span>
            <input
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              placeholder="web-console"
            />
          </label>
          <label className="form-grid__wide">
            <span>Conversation ID</span>
            <input
              value={conversationId}
              onChange={(e) => setConversationId(e.target.value)}
              placeholder="conv-… (leave blank to match any conversation in the session)"
            />
          </label>
        </div>
        {!scopeReady && !providersState.loading && providers.length > 0 ? (
          <p className="inline-feedback" style={{ marginTop: "0.5rem" }}>
            Enter a conversation ID or session ID to load memory.
          </p>
        ) : null}
        {!providers.length && !providersState.loading ? (
          <EmptyState
            title="No providers"
            description="No LLM providers configured. Add a provider from the Providers page to inspect memory."
          />
        ) : null}
      </SectionCard>

      <SectionCard
        title="Persisted memory"
        subtitle={`${memoryState.data?.memory_count ?? 0} stored messages · max ${memoryState.data?.max_stored_turns ?? "—"} turns`}
        actions={(
          <div className="chat-card-actions">
            <label className="chat-inline-field">
              <span>TTL hours</span>
              <input
                aria-label="Prune older than hours"
                inputMode="numeric"
                value={pruneHours}
                onChange={(e) => setPruneHours(e.target.value)}
              />
            </label>
            <button
              className="button button--ghost button--small"
              onClick={handlePrune}
              type="button"
              disabled={!effectiveProviderId || pruning}
            >
              {pruning ? "Pruning…" : "Prune expired"}
            </button>
          </div>
        )}
      >
        {memoryFeedback ? (
          <p className={`inline-feedback inline-feedback--${memoryFeedback.tone}`}>{memoryFeedback.text}</p>
        ) : null}
        {memoryState.loading && !memoryState.data ? <div className="page-state">Loading memory…</div> : null}
        {memoryState.error ? <div className="page-state page-state--error">{memoryState.error}</div> : null}
        {transcript.length > 0 ? (
          <div className="chat-transcript">
            {transcript.map((msg: ChatMemoryItem) => (
              <article key={msg.id} className={`chat-bubble chat-bubble--${msg.role}`}>
                <header>
                  <strong>{msg.role}</strong>
                  <span>{formatTimestamp(msg.created_at)}</span>
                </header>
                <p>{msg.content}</p>
              </article>
            ))}
          </div>
        ) : scopeReady && !memoryState.loading ? (
          <EmptyState
            title="No stored memory"
            description="No messages found for this scope. Send messages from the chat page first."
          />
        ) : null}
      </SectionCard>

      <SectionCard
        title="Conversation summary"
        subtitle="LLM-generated or fallback summary for the active scope"
        actions={(
          <div className="chat-card-actions">
            <button
              className="button button--ghost button--small"
              onClick={handleRefresh}
              type="button"
              disabled={!scopeReady || refreshing || regenerating}
            >
              {refreshing ? "Refreshing…" : "Refresh"}
            </button>
            <button
              className="button button--ghost button--small"
              onClick={handleRegenerate}
              type="button"
              disabled={!scopeReady || regenerating || refreshing}
            >
              {regenerating ? "Regenerating…" : "Regenerate"}
            </button>
          </div>
        )}
      >
        {summaryFeedback ? (
          <p className={`inline-feedback inline-feedback--${summaryFeedback.tone}`}>{summaryFeedback.text}</p>
        ) : null}
        {summaryState.loading && !summaryState.data ? <div className="page-state">Loading summary…</div> : null}
        {summaryState.error ? <div className="page-state page-state--error">{summaryState.error}</div> : null}
        {summaryState.data?.summary ? (
          <div className="chat-summary-panel">
            <div className="chat-summary-meta">
              <span>{summaryState.data.summary.source.toUpperCase()}</span>
              <strong>{summaryState.data.summary.memory_count} messages</strong>
            </div>
            <p>{summaryState.data.summary.summary_text}</p>
            <small>Updated {formatTimestamp(summaryState.data.summary.updated_at)}</small>
          </div>
        ) : scopeReady && !summaryState.loading ? (
          <EmptyState
            title="No summary yet"
            description="A summary will be generated automatically after enough turns. Use Regenerate to force one now."
          />
        ) : null}
      </SectionCard>
    </div>
  );
}
