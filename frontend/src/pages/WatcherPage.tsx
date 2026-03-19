import { EmptyState } from "../components/EmptyState";
import { SectionCard } from "../components/SectionCard";
import { StatusBadge } from "../components/StatusBadge";
import { usePolling } from "../hooks/usePolling";
import { platformApi } from "../services/platformApi";
import { formatTimestamp } from "../utils/format";

export function WatcherPage() {
  const health = usePolling(() => platformApi.health(), 10000);
  const packagesState = usePolling(() => platformApi.listPackages(), 15000);
  const schedulesState = usePolling(() => platformApi.listSchedules(), 15000);

  const packages = packagesState.data || [];
  const recentPackages = [...packages].sort((a, b) => {
    const left = a.created_at ? new Date(a.created_at).getTime() : 0;
    const right = b.created_at ? new Date(b.created_at).getTime() : 0;
    return right - left;
  });
  const blockedSchedules = packages.filter((pkg) => pkg.schedule_activation_blocked);
  const secretsPending = packages.filter((pkg) => pkg.missing_secret_keys.length > 0);
  const activeSchedules = (schedulesState.data || []).filter((schedule) => schedule.is_active).length;

  return (
    <div className="page-grid">
      <section className="hero-panel">
        <div>
          <span className="eyebrow">Watcher visibility</span>
          <h3>Inferred package watcher status</h3>
          <p>
            The backend does not expose a dedicated watcher heartbeat endpoint yet. This view derives watcher health from API availability,
            package registration activity, and schedule activation blockers.
          </p>
        </div>
        <StatusBadge status={health.data?.status || "unknown"} />
      </section>

      <section className="stats-grid stats-grid--three">
        <article className="stat-card">
          <span>Registered packages</span>
          <strong>{packages.length}</strong>
        </article>
        <article className="stat-card">
          <span>Active schedules</span>
          <strong>{activeSchedules}</strong>
        </article>
        <article className="stat-card">
          <span>Blocked schedules</span>
          <strong>{blockedSchedules.length}</strong>
        </article>
      </section>

      <SectionCard title="Recent package registrations" subtitle="Latest package records observed by the platform">
        {recentPackages.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Package</th>
                  <th>Filename</th>
                  <th>Created</th>
                  <th>Schedule</th>
                  <th>Missing secrets</th>
                </tr>
              </thead>
              <tbody>
                {recentPackages.slice(0, 10).map((pkg) => (
                  <tr key={pkg.id}>
                    <td>
                      <strong>{pkg.name}</strong>
                      <div className="subtle-cell">#{pkg.id}</div>
                    </td>
                    <td>{pkg.filename || "-"}</td>
                    <td>{formatTimestamp(pkg.created_at)}</td>
                    <td><StatusBadge status={pkg.schedule_activation_blocked ? "blocked" : (pkg.schedule_enabled ? "active" : "inactive")} /></td>
                    <td>{pkg.missing_secret_keys.join(", ") || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="No packages recorded" description="Once packages are registered by the watcher or metadata API, they will appear here." />
        )}
      </SectionCard>

      <SectionCard title="Attention required" subtitle="Packages waiting on secrets before automation can activate">
        {secretsPending.length ? (
          <ul className="stack-list">
            {secretsPending.map((pkg) => (
              <li key={pkg.id}>
                <div>
                  <strong>{pkg.name}</strong>
                  <p>Missing {pkg.missing_secret_keys.length} required secret(s)</p>
                </div>
                <span>{pkg.missing_secret_keys.join(", ")}</span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No blocked registrations" description="All currently registered packages have the required secret inventory for schedule activation." />
        )}
      </SectionCard>
    </div>
  );
}