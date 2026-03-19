import { useMemo, useState } from "react";
import { EmptyState } from "../components/EmptyState";
import { SectionCard } from "../components/SectionCard";
import { StatusBadge } from "../components/StatusBadge";
import { usePolling } from "../hooks/usePolling";
import { platformApi } from "../services/platformApi";
import type { RunEvent, RunSummary } from "../types/api";
import { formatTimestamp, safeJson } from "../utils/format";

interface AggregatedEvent extends RunEvent {
  runSummary: RunSummary;
}

export function AuditPage() {
  const runsState = usePolling(() => platformApi.listRuns(), 5000);
  const [filter, setFilter] = useState("");

  const auditState = usePolling<AggregatedEvent[]>(
    async () => {
      const recentRuns = (runsState.data || []).slice(0, 8);
      const eventGroups = await Promise.all(
        recentRuns.map(async (run) => {
          const events = await platformApi.getRunEvents(run.id);
          return events.map((event) => ({ ...event, runSummary: run }));
        }),
      );

      return eventGroups.flat().sort((left, right) => {
        const leftTs = left.ts ? new Date(left.ts).getTime() : 0;
        const rightTs = right.ts ? new Date(right.ts).getTime() : 0;
        return rightTs - leftTs;
      });
    },
    5000,
    [runsState.data],
  );

  const filteredEvents = useMemo(() => {
    const search = filter.trim().toLowerCase();
    if (!search) {
      return auditState.data || [];
    }
    return (auditState.data || []).filter((event) => {
      const haystack = [
        event.type,
        event.level,
        event.category,
        event.source,
        event.message,
        event.runSummary.id.toString(),
        event.runSummary.agent_package_id.toString(),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(search);
    });
  }, [auditState.data, filter]);

  const warningCount = filteredEvents.filter((event) => (event.level || "").toLowerCase() === "warning").length;
  const errorCount = filteredEvents.filter((event) => (event.level || "").toLowerCase() === "error").length;

  return (
    <div className="page-grid">
      <section className="stats-grid stats-grid--three">
        <article className="stat-card">
          <span>Visible audit events</span>
          <strong>{filteredEvents.length}</strong>
        </article>
        <article className="stat-card">
          <span>Warnings</span>
          <strong>{warningCount}</strong>
        </article>
        <article className="stat-card">
          <span>Errors</span>
          <strong>{errorCount}</strong>
        </article>
      </section>

      <SectionCard
        title="Cross-run audit feed"
        subtitle="Aggregated event stream across the most recent runs"
        actions={<input className="filter-input" placeholder="Filter by run, type, source, or level" value={filter} onChange={(event) => setFilter(event.target.value)} />}
      >
        {auditState.loading ? <div className="page-state">Loading audit events...</div> : null}
        {auditState.error ? <div className="page-state page-state--error">{auditState.error}</div> : null}
        {filteredEvents.length ? (
          <div className="audit-feed">
            {filteredEvents.map((event) => (
              <article className="audit-feed__item" key={`${event.run_id}-${event.id}`}>
                <div className="audit-feed__header">
                  <div>
                    <strong>{event.type}</strong>
                    <p>Run #{event.runSummary.id} · Package #{event.runSummary.agent_package_id}</p>
                  </div>
                  <div className="audit-feed__status-group">
                    <StatusBadge status={event.level || "info"} />
                    <span>{formatTimestamp(event.ts)}</span>
                  </div>
                </div>
                <p>{event.message || "No message"}</p>
                {event.payload_jason ? <pre>{safeJson(event.payload_jason)}</pre> : null}
              </article>
            ))}
          </div>
        ) : !auditState.loading ? (
          <EmptyState title="No audit events visible" description="Run activity that emits structured events will appear here once workers record them." />
        ) : null}
      </SectionCard>
    </div>
  );
}