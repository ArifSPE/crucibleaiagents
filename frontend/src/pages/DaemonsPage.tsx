import { EmptyState } from "../components/EmptyState";
import { SectionCard } from "../components/SectionCard";
import { StatusBadge } from "../components/StatusBadge";
import { usePolling } from "../hooks/usePolling";
import { platformApi } from "../services/platformApi";
import { formatTimestamp } from "../utils/format";

export function DaemonsPage() {
  const packagesState = usePolling(() => platformApi.listPackages(), 10000);
  const runsState = usePolling(() => platformApi.listRuns(), 5000);

  const daemonPackages = (packagesState.data || []).filter((pkg) => pkg.runtime_mode === "daemon");
  const daemonRuns = (runsState.data || []).filter((run) => run.runtime_mode === "daemon");
  const latestRunByPackage = new Map<number, (typeof daemonRuns)[number]>();

  for (const run of daemonRuns) {
    if (!latestRunByPackage.has(run.agent_package_id)) {
      latestRunByPackage.set(run.agent_package_id, run);
    }
  }

  const activeCount = daemonRuns.filter((run) => run.status === "running").length;
  const restartTotal = daemonRuns.reduce((sum, run) => sum + (run.restart_count || 0), 0);
  const exposedCount = daemonRuns.filter((run) => run.exposed_port).length;

  return (
    <div className="page-grid">
      <section className="stats-grid stats-grid--three">
        <article className="stat-card">
          <span>Daemon packages</span>
          <strong>{daemonPackages.length}</strong>
        </article>
        <article className="stat-card">
          <span>Active daemon runs</span>
          <strong>{activeCount}</strong>
        </article>
        <article className="stat-card">
          <span>Total restarts</span>
          <strong>{restartTotal}</strong>
        </article>
      </section>

      <SectionCard title="Daemon fleet" subtitle="Package-level view of long-running services and the latest daemon run">
        {daemonPackages.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Package</th>
                  <th>Deployment</th>
                  <th>Auto-start</th>
                  <th>Latest run</th>
                  <th>Port</th>
                  <th>Last health</th>
                  <th>Restarts</th>
                </tr>
              </thead>
              <tbody>
                {daemonPackages.map((pkg) => {
                  const run = latestRunByPackage.get(pkg.id);
                  return (
                    <tr key={pkg.id}>
                      <td>
                        <strong>{pkg.name}</strong>
                        <div className="subtle-cell">#{pkg.id}</div>
                      </td>
                      <td>{pkg.deployment}</td>
                      <td><StatusBadge status={pkg.daemon_auto_start ? "active" : "inactive"} /></td>
                      <td>{run ? <StatusBadge status={run.status} /> : "no run yet"}</td>
                      <td>{run?.exposed_port || pkg.exposed_port || "-"}</td>
                      <td>{formatTimestamp(run?.last_health_check || null)}</td>
                      <td>{run?.restart_count || 0}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="No daemon packages" description="Register packages with runtime_mode set to daemon to monitor persistent services here." />
        )}
      </SectionCard>

      <SectionCard title="Published daemon endpoints" subtitle="Daemon services exposing host ports">
        {exposedCount ? (
          <ul className="stack-list">
            {daemonRuns.filter((run) => run.exposed_port).map((run) => (
              <li key={run.id}>
                <div>
                  <strong>Run #{run.id}</strong>
                  <p>Package #{run.agent_package_id}</p>
                </div>
                <a className="inline-link" href={`http://localhost:${run.exposed_port}`} rel="noreferrer" target="_blank">
                  localhost:{run.exposed_port}
                </a>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No exposed daemon ports" description="Daemon runs with exposed ports will show quick access links here." />
        )}
      </SectionCard>
    </div>
  );
}