import { useEffect, useState } from "react";
import { EmptyState } from "../components/EmptyState";
import { LogConsole } from "../components/LogConsole";
import { SectionCard } from "../components/SectionCard";
import { StatusBadge } from "../components/StatusBadge";
import { Tabs } from "../components/Tabs";
import { usePolling } from "../hooks/usePolling";
import { platformApi } from "../services/platformApi";
import { formatDuration, formatTimestamp } from "../utils/format";

export function RunsPage() {
  const runsState = usePolling(() => platformApi.listRuns(), 5000);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<string>("runs");
  const selectedRun = (runsState.data || []).find((run) => run.id === selectedRunId) || null;

  const logsState = usePolling(
    () => (selectedRunId ? platformApi.getRunLogs(selectedRunId) : Promise.resolve([])),
    3000,
    [selectedRunId],
  );
  const eventsState = usePolling(
    () => (selectedRunId ? platformApi.getRunEvents(selectedRunId) : Promise.resolve([])),
    3000,
    [selectedRunId],
  );

  useEffect(() => {
    if (!selectedRunId && runsState.data?.length) {
      setSelectedRunId(runsState.data[0].id);
    }
  }, [runsState.data, selectedRunId]);

  return (
    <div className="page-grid">
      <SectionCard title="Run execution & monitoring" subtitle="Navigate between runs, events, and logs for complete execution visibility">
        {runsState.loading && !runsState.data ? <div className="page-state">Loading runs...</div> : null}
        {runsState.error && !runsState.data ? <div className="page-state page-state--error">{runsState.error}</div> : null}

        {runsState.data || runsState.error ? (
          <Tabs
            tabs={[
              {
                id: "runs",
                label: "Runs",
                content:
                  runsState.data?.length ? (
                    <div className="table-wrap">
                      <table className="data-table data-table--interactive">
                        <thead>
                          <tr>
                            <th>Run</th>
                            <th>Package</th>
                            <th>Status</th>
                            <th>Mode</th>
                            <th>Started</th>
                            <th>Duration</th>
                          </tr>
                        </thead>
                        <tbody>
                          {runsState.data.map((run) => (
                            <tr
                              key={run.id}
                              className={run.id === selectedRunId ? "selected-row" : ""}
                              onClick={() => {
                                setSelectedRunId(run.id);
                              }}
                            >
                              <td>#{run.id}</td>
                              <td>{run.agent_package_id}</td>
                              <td>
                                <StatusBadge status={run.status} />
                              </td>
                              <td>{run.runtime_mode || "batch"}</td>
                              <td>{formatTimestamp(run.started_at)}</td>
                              <td>{formatDuration(run.started_at, run.completed_at)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <EmptyState title="No runs available" description="Trigger package execution from the Packages page to start collecting run data." />
                  ),
              },
              {
                id: "events",
                label: "Events",
                content: selectedRun ? (
                  <div>
                    <div className="page-state-subtitle">
                      Showing events for run #{selectedRun.id} (package #{selectedRun.agent_package_id})
                    </div>
                    {eventsState.data?.length ? (
                      <div className="table-wrap">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Time</th>
                              <th>Type</th>
                              <th>Level</th>
                              <th>Source</th>
                              <th>Message</th>
                            </tr>
                          </thead>
                          <tbody>
                            {eventsState.data.map((event) => (
                              <tr key={event.id}>
                                <td>{formatTimestamp(event.ts)}</td>
                                <td>{event.type}</td>
                                <td>{event.level || "-"}</td>
                                <td>{event.source || "-"}</td>
                                <td>{event.message || "-"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <EmptyState title="No events for this run" description="Select a different run from the Runs tab to view its events." />
                    )}
                  </div>
                ) : (
                  <EmptyState title="Select a run first" description="Go to the Runs tab and click on a run to view its events here." />
                ),
              },
              {
                id: "logs",
                label: "Logs",
                content: selectedRun ? (
                  <div>
                    <div className="page-state-subtitle">
                      Showing logs for run #{selectedRun.id} (package #{selectedRun.agent_package_id})
                    </div>
                    <LogConsole logs={logsState.data || []} />
                  </div>
                ) : (
                  <EmptyState title="Select a run first" description="Go to the Runs tab and click on a run to view its logs here." />
                ),
              },
            ]}
            activeTabId={activeTab}
            onTabChange={setActiveTab}
          />
        ) : null}
      </SectionCard>
    </div>
  );
}