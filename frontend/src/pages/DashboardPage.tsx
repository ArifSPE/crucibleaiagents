import { Link } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";
import { SectionCard } from "../components/SectionCard";
import { StatusBadge } from "../components/StatusBadge";
import { usePolling } from "../hooks/usePolling";
import { platformApi } from "../services/platformApi";
import type { AgentPackage, HealthResponse, LlmProvider, PackageSchedule, RunSummary } from "../types/api";
import { formatDuration, formatTimestamp } from "../utils/format";

interface DashboardViewProps {
  health: HealthResponse | null;
  packages: AgentPackage[];
  runs: RunSummary[];
  schedules: PackageSchedule[];
  providers: LlmProvider[];
  loading: boolean;
  error: string | null;
}

export function DashboardView({ health, packages, runs, schedules, providers, loading, error }: DashboardViewProps) {
  const runningCount = runs.filter((run) => run.status === "running").length;
  const failedCount = runs.filter((run) => run.status === "failed").length;
  const daemonPackages = packages.filter((pkg) => pkg.runtime_mode === "daemon").length;

  if (loading) {
    return <div className="page-state">Loading platform dashboard...</div>;
  }

  if (error) {
    return <div className="page-state page-state--error">{error}</div>;
  }

  return (
    <div className="page-grid">
      <section className="hero-panel">
        <div>
          <span className="eyebrow">System health</span>
          <h3>Backend {health?.service || "api"}</h3>
          <p>Use this dashboard to track throughput, daemon availability, and integration readiness.</p>
        </div>
        <StatusBadge status={health?.status || "unknown"} />
      </section>

      <section className="stats-grid">
        <article className="stat-card">
          <span>Total packages</span>
          <strong>{packages.length}</strong>
        </article>
        <article className="stat-card">
          <span>Running runs</span>
          <strong>{runningCount}</strong>
        </article>
        <article className="stat-card">
          <span>Failed runs</span>
          <strong>{failedCount}</strong>
        </article>
        <article className="stat-card">
          <span>Daemon packages</span>
          <strong>{daemonPackages}</strong>
        </article>
      </section>

      <SectionCard title="Recent runs" subtitle="Latest execution activity across the platform">
        {runs.length ? (
          <div className="table-wrap">
            <table className="data-table">
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
                {runs.slice(0, 8).map((run) => (
                  <tr key={run.id}>
                    <td>#{run.id}</td>
                    <td><Link to={`/packages?package=${run.agent_package_id}`}>#{run.agent_package_id}</Link></td>
                    <td><StatusBadge status={run.status} /></td>
                    <td>{run.runtime_mode || "batch"}</td>
                    <td>{formatTimestamp(run.started_at)}</td>
                    <td>{formatDuration(run.started_at, run.completed_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="No runs yet" description="Create a package run from the Packages page to see execution history here." />
        )}
      </SectionCard>

      <SectionCard title="Schedules" subtitle="Configured automation windows">
        {schedules.length ? (
          <ul className="stack-list">
            {schedules.slice(0, 6).map((schedule) => (
              <li key={schedule.id}>
                <div>
                  <strong>Package #{schedule.package_id}</strong>
                  <p>{schedule.schedule_type}</p>
                </div>
                <div>
                  <StatusBadge status={schedule.is_active ? "active" : "inactive"} />
                  <span>{formatTimestamp(schedule.next_run_time)}</span>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No schedules configured" description="Create interval or cron schedules for packages from the Packages page." />
        )}
      </SectionCard>

      <SectionCard title="Providers" subtitle="Configured model backends">
        {providers.length ? (
          <ul className="pill-list">
            {providers.map((provider) => (
              <li key={provider.id}>
                <strong>{provider.provider}</strong>
                <span>{provider.endpoint || "No endpoint recorded"}</span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No providers configured" description="Add LLM providers to support agents that depend on managed model access." />
        )}
      </SectionCard>
    </div>
  );
}

export function DashboardPage() {
  const health = usePolling(() => platformApi.health(), 10000);
  const packages = usePolling(() => platformApi.listPackages(), 15000);
  const runs = usePolling(() => platformApi.listRuns(), 5000);
  const schedules = usePolling(() => platformApi.listSchedules(), 15000);
  const providers = usePolling(() => platformApi.listProviders(), 15000);

  return (
    <DashboardView
      health={health.data}
      packages={packages.data || []}
      runs={runs.data || []}
      schedules={schedules.data || []}
      providers={providers.data || []}
      loading={health.loading || packages.loading || runs.loading || schedules.loading || providers.loading}
      error={health.error || packages.error || runs.error || schedules.error || providers.error}
    />
  );
}