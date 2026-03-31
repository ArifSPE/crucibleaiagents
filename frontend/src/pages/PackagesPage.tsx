import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  type SortingState,
  useReactTable,
} from "@tanstack/react-table";
import { EmptyState } from "../components/EmptyState";
import { SectionCard } from "../components/SectionCard";
import { StatusBadge } from "../components/StatusBadge";
import { Tabs } from "../components/Tabs";
import { usePolling } from "../hooks/usePolling";
import { platformApi } from "../services/platformApi";
import type { AgentPackage, PackageSchedule, PackageSecret, RunSummary, ScheduleUpsertRequest, SecretUpsertRequest } from "../types/api";
import { formatTimestamp } from "../utils/format";

type RunDrilldownView = "events" | "logs";

function parsePositiveId(value: string | null): number | null {
  if (!value) {
    return null;
  }
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    return null;
  }
  return parsed;
}

function parseDrilldownTab(value: string | null): RunDrilldownView {
  return value === "logs" ? "logs" : "events";
}

export function PackagesPage() {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const isInternalSearchUpdateRef = useRef(false);
  const packagesState = usePolling(() => platformApi.listPackages(), 10000);
  const [selectedPackageId, setSelectedPackageId] = useState<number | null>(() => parsePositiveId(searchParams.get("package")));
  const [selectedRunId, setSelectedRunId] = useState<number | null>(() => parsePositiveId(searchParams.get("run")));
  const [runDrilldownView, setRunDrilldownView] = useState<RunDrilldownView>(() => parseDrilldownTab(searchParams.get("tab")));
  const [scheduleForm, setScheduleForm] = useState<ScheduleUpsertRequest>({ schedule_type: "interval", interval_seconds: 300, enabled: true });
  const [secretForm, setSecretForm] = useState<SecretUpsertRequest>({ key_name: "", value: "" });
  const [feedback, setFeedback] = useState<string | null>(null);
  const [packageFilterText, setPackageFilterText] = useState("");
  const [packageSorting, setPackageSorting] = useState<SortingState>([{ id: "id", desc: true }]);

  const selectedPackage = (packagesState.data || []).find((pkg) => pkg.id === selectedPackageId) || null;
  const schedulesState = usePolling<PackageSchedule[]>(
    () => (selectedPackageId ? platformApi.listPackageSchedules(selectedPackageId) : Promise.resolve([])),
    10000,
    [selectedPackageId],
  );
  const secretsState = usePolling<PackageSecret[]>(
    () => (selectedPackageId ? platformApi.listPackageSecrets(selectedPackageId) : Promise.resolve([])),
    10000,
    [selectedPackageId],
  );
  const runsState = usePolling<RunSummary[]>(
    () => (selectedPackageId ? platformApi.getPackageRuns(selectedPackageId) : Promise.resolve([])),
    5000,
    [selectedPackageId],
  );

  const runLogsState = usePolling(
    () => (selectedRunId ? platformApi.getRunLogs(selectedRunId) : Promise.resolve([])),
    3000,
    [selectedRunId],
  );

  const runEventsState = usePolling(
    () => (selectedRunId ? platformApi.getRunEvents(selectedRunId) : Promise.resolve([])),
    3000,
    [selectedRunId],
  );

  const selectedRun = useMemo(
    () => (runsState.data || []).find((run) => run.id === selectedRunId) || null,
    [runsState.data, selectedRunId],
  );
  const requiredSecretKeys = selectedPackage?.secret_keys || [];
  const requiredSecretKeysSignature = requiredSecretKeys.join("|");
  const missingSecretKeys = selectedPackage?.missing_secret_keys || [];
  const isPackageOnHold = missingSecretKeys.length > 0;
  const secretsForSelectedPackage = useMemo(
    () => (secretsState.data || []).filter((secret) => secret.package_id === selectedPackageId),
    [secretsState.data, selectedPackageId],
  );
  const secretKeyOptions = useMemo(() => {
    const keys = new Set<string>();
    for (const key of requiredSecretKeys) {
      const normalized = String(key).trim();
      if (normalized) {
        keys.add(normalized);
      }
    }
    for (const key of missingSecretKeys) {
      const normalized = String(key).trim();
      if (normalized) {
        keys.add(normalized);
      }
    }
    for (const secret of secretsForSelectedPackage) {
      const normalized = String(secret.key_name).trim();
      if (normalized) {
        keys.add(normalized);
      }
    }
    return Array.from(keys);
  }, [missingSecretKeys, requiredSecretKeys, secretsForSelectedPackage]);
  const secretKeyOptionsSignature = secretKeyOptions.join("|");
  const secretRows = useMemo(() => {
    const secretByKey = new Map(secretsForSelectedPackage.map((secret) => [secret.key_name, secret]));

    if (!requiredSecretKeys.length) {
      return secretsForSelectedPackage.map((secret) => ({
        key_name: secret.key_name,
        updated_at: secret.updated_at,
        is_missing: false,
      }));
    }

    const rows = requiredSecretKeys.map((key_name) => {
      const existing = secretByKey.get(key_name);
      return {
        key_name,
        updated_at: existing?.updated_at || null,
        is_missing: missingSecretKeys.includes(key_name),
      };
    });

    for (const secret of secretsForSelectedPackage) {
      if (!requiredSecretKeys.includes(secret.key_name)) {
        rows.push({
          key_name: secret.key_name,
          updated_at: secret.updated_at,
          is_missing: false,
        });
      }
    }

    return rows;
  }, [missingSecretKeys, requiredSecretKeys, secretsForSelectedPackage]);

  const filteredPackages = useMemo(() => {
    const query = packageFilterText.trim().toLowerCase();
    if (!query) {
      return packagesState.data || [];
    }
    return (packagesState.data || []).filter((pkg) => {
      const status = (pkg.missing_secret_keys || []).length
        ? `on hold ${pkg.missing_secret_keys.length} secrets missing`
        : "ready";
      const searchable = [
        String(pkg.id),
        pkg.name,
        pkg.version,
        pkg.language || "",
        pkg.deployment || "",
        pkg.runtime_mode || "batch",
        status,
      ]
        .join(" ")
        .toLowerCase();
      return searchable.includes(query);
    });
  }, [packageFilterText, packagesState.data]);

  const packageColumnHelper = createColumnHelper<AgentPackage>();

  const packageColumns = useMemo(
    () => [
      packageColumnHelper.accessor("id", {
        id: "id",
        header: "ID",
        cell: (info) => info.getValue(),
      }),
      packageColumnHelper.accessor("name", {
        id: "name",
        header: "Name",
        cell: (info) => info.getValue(),
      }),
      packageColumnHelper.accessor("version", {
        id: "version",
        header: "Version",
        cell: (info) => info.getValue(),
      }),
      packageColumnHelper.accessor((row) => row.language || "-", {
        id: "language",
        header: "Language",
        cell: (info) => info.getValue(),
      }),
      packageColumnHelper.accessor("deployment", {
        id: "deployment",
        header: "Deployment",
        cell: (info) => info.getValue(),
      }),
      packageColumnHelper.accessor((row) => row.runtime_mode || "batch", {
        id: "runtime_mode",
        header: "Runtime",
        cell: (info) => info.getValue(),
      }),
      packageColumnHelper.display({
        id: "status",
        header: "Status",
        cell: ({ row }) =>
          (row.original.missing_secret_keys || []).length
            ? `On hold (${row.original.missing_secret_keys?.length || 0} secrets missing)`
            : "Ready",
      }),
    ],
    [packageColumnHelper],
  );

  const packageTable = useReactTable({
    data: filteredPackages,
    columns: packageColumns,
    state: {
      sorting: packageSorting,
    },
    onSortingChange: setPackageSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const visiblePackageRows = packageTable.getRowModel().rows.length;

  useEffect(() => {
    if (!selectedPackageId && packagesState.data?.length) {
      setSelectedPackageId(packagesState.data[0].id);
    }
  }, [packagesState.data, selectedPackageId]);

  useEffect(() => {
    if (isInternalSearchUpdateRef.current) {
      isInternalSearchUpdateRef.current = false;
      return;
    }

    const fromUrl = new URLSearchParams(location.search);
    const packageFromUrl = parsePositiveId(fromUrl.get("package"));
    const runFromUrl = parsePositiveId(fromUrl.get("run"));
    const tabFromUrl = parseDrilldownTab(fromUrl.get("tab"));

    setSelectedPackageId(packageFromUrl);
    setSelectedRunId(runFromUrl);
    setRunDrilldownView(tabFromUrl);
  }, [location.search]);

  useEffect(() => {
    const nextParams = new URLSearchParams();
    if (selectedPackageId) {
      nextParams.set("package", String(selectedPackageId));
    }
    if (selectedRunId) {
      nextParams.set("run", String(selectedRunId));
    }
    nextParams.set("tab", runDrilldownView);

    const nextSerialized = nextParams.toString();
    const currentSerialized = location.search.startsWith("?") ? location.search.slice(1) : location.search;
    if (nextSerialized !== currentSerialized) {
      isInternalSearchUpdateRef.current = true;
      setSearchParams(nextParams, { replace: true });
    }
  }, [location.search, runDrilldownView, selectedPackageId, selectedRunId, setSearchParams]);

  useEffect(() => {
    const firstRun = runsState.data?.[0];
    if (!selectedRunId && firstRun) {
      setSelectedRunId(firstRun.id);
    }

    if (selectedRunId && runsState.data?.every((run) => run.id !== selectedRunId)) {
      setSelectedRunId(firstRun ? firstRun.id : null);
    }
  }, [runsState.data, selectedRunId]);

  useEffect(() => {
    if (selectedRunId && selectedPackageId && runsState.data?.every((run) => run.id !== selectedRunId)) {
      setSelectedRunId(null);
    }
  }, [runsState.data, selectedPackageId, selectedRunId]);

  useEffect(() => {
    if (!secretKeyOptions.length) {
      return;
    }

    setSecretForm((prev) => {
      if (secretKeyOptions.includes(prev.key_name)) {
        return prev;
      }
      return { ...prev, key_name: secretKeyOptions[0] };
    });
  }, [selectedPackageId, requiredSecretKeysSignature, secretKeyOptionsSignature]);

  async function handleRunPackage(packageId: number) {
    setFeedback(null);
    try {
      const run = await platformApi.createRun(packageId);
      await runsState.refresh();
      setSelectedRunId(run.id);
      setRunDrilldownView("events");
      setFeedback(`Run #${run.id} created for package #${packageId}.`);
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "Failed to create run.");
    }
  }



  async function handleCreateSchedule(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedPackageId) {
      return;
    }
    if (isPackageOnHold) {
      setFeedback(`Package is on hold. Set required secrets first: ${missingSecretKeys.join(", ")}`);
      return;
    }
    setFeedback(null);
    try {
      await platformApi.createPackageSchedule(selectedPackageId, scheduleForm);
      await schedulesState.refresh();
      await packagesState.refresh();
      setFeedback("Schedule created successfully.");
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "Failed to create schedule.");
    }
  }

  async function handleCreateSecret(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedPackageId) {
      return;
    }
    const keyName = secretForm.key_name.trim() || secretKeyOptions[0] || "";
    if (!keyName) {
      setFeedback("Select an environment key before storing the secret value.");
      return;
    }
    setFeedback(null);
    try {
      await platformApi.createPackageSecret(selectedPackageId, {
        key_name: keyName,
        value: secretForm.value,
      });
      await secretsState.refresh();
      await schedulesState.refresh();
      await packagesState.refresh();
      setSecretForm({
        key_name: secretKeyOptions.length ? keyName : "",
        value: "",
      });
      window.alert(`Secret '${keyName}' stored successfully.`);
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "Failed to store secret.");
    }
  }

  return (
    <div className="page-grid page-grid--packages">
      <SectionCard title="Package catalog" subtitle="Select a package to drill into runs, events, and logs">
        {packagesState.loading ? <div className="page-state">Loading packages...</div> : null}
        {packagesState.error ? <div className="page-state page-state--error">{packagesState.error}</div> : null}
        {packagesState.data?.length ? (
          <div className="catalog-table-shell">
            <div className="catalog-table-toolbar">
              <p>
                Showing {visiblePackageRows} of {packagesState.data.length} package rows
              </p>
              <input
                className="catalog-filter-input"
                onChange={(event) => setPackageFilterText(event.target.value)}
                placeholder="Filter packages..."
                value={packageFilterText}
              />
            </div>
            <div className="catalog-grid">
              <div className="table-wrap">
                <table className="data-table catalog-table">
                  <thead>
                    {packageTable.getHeaderGroups().map((headerGroup) => (
                      <tr key={headerGroup.id}>
                        {headerGroup.headers.map((header) => {
                          const canSort = header.column.getCanSort();
                          const sortState = header.column.getIsSorted();
                          return (
                            <th
                              key={header.id}
                              className={canSort ? "catalog-table__sortable" : ""}
                              onClick={canSort ? header.column.getToggleSortingHandler() : undefined}
                            >
                              <span>
                                {flexRender(header.column.columnDef.header, header.getContext())}
                                {sortState === "asc" ? " ▲" : sortState === "desc" ? " ▼" : ""}
                              </span>
                            </th>
                          );
                        })}
                      </tr>
                    ))}
                  </thead>
                  <tbody>
                    {packageTable.getRowModel().rows.map((row) => (
                      <tr
                        className={row.original.id === selectedPackageId ? "selected-row" : ""}
                        key={row.id}
                        onClick={() => setSelectedPackageId(row.original.id)}
                      >
                        {row.getVisibleCells().map((cell) => (
                          <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        ) : !packagesState.loading ? (
          <EmptyState title="No packages registered" description="No package metadata found yet. Register packages through your deployment flow and they will appear here." />
        ) : null}
      </SectionCard>

      <SectionCard
        title={selectedPackage ? `Package #${selectedPackage.id}: ${selectedPackage.name}` : "Package details"}
        subtitle="Configure secrets and schedules, view run events and logs"
        actions={selectedPackage ? (
          <button
            className="button"
            onClick={() => void handleRunPackage(selectedPackage.id)}
            type="button"
            disabled={isPackageOnHold}
            title={isPackageOnHold ? "Set required secrets before running this package" : "Run package now"}
          >
            Run now
          </button>
        ) : null}
      >
        {selectedPackage ? (
          <>
            <div className="package-meta-compact">
              <div className="meta-grid">
                <div><strong>Version</strong> {selectedPackage.version}</div>
                <div><strong>Language</strong> {selectedPackage.language || "-"}</div>
                <div><strong>Deployment</strong> {selectedPackage.deployment}</div>
                <div><strong>Runtime</strong> {selectedPackage.runtime_mode || "batch"}</div>
              </div>
            </div>

            {isPackageOnHold ? (
              <div className="package-hold-alert">
                <strong>Package on hold:</strong> required secrets are missing ({missingSecretKeys.join(", ")}).
                Add these secrets below before running or activating schedules.
              </div>
            ) : null}

            <div className="package-config-section">
              {(requiredSecretKeys.length > 0 || secretsForSelectedPackage.length > 0 || secretsState.loading) ? (
                <div className="config-column">
                  <h3>Secrets</h3>
                  {secretRows.length ? (
                    <ul className="stack-list">
                      {secretRows.map((secret) => (
                        <li key={secret.key_name}>
                          <div>
                            <strong>{secret.key_name}</strong>
                            <p>{secret.is_missing ? "Value: missing" : "Value: ...."}</p>
                            <p>{secret.is_missing ? "Set this secret to enable runs and schedules." : `Updated ${formatTimestamp(secret.updated_at)}`}</p>
                          </div>
                          <StatusBadge status={secret.is_missing ? "blocked" : "active"} />
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <EmptyState title="No secrets stored" description="Save required placeholders before enabling schedules that depend on secret injection." />
                  )}
                  <form className="compact-form" onSubmit={handleCreateSecret}>
                    {secretKeyOptions.length ? (
                      <select value={secretForm.key_name} onChange={(event) => setSecretForm((prev) => ({ ...prev, key_name: event.target.value }))} required>
                        {secretKeyOptions.map((key) => (
                          <option key={key} value={key}>{key}</option>
                        ))}
                      </select>
                    ) : (
                      <input placeholder="Environment key" value={secretForm.key_name} onChange={(event) => setSecretForm((prev) => ({ ...prev, key_name: event.target.value }))} required />
                    )}
                    <input placeholder="Secret value" type="password" value={secretForm.value} onChange={(event) => setSecretForm((prev) => ({ ...prev, value: event.target.value }))} required />
                    <button className="button" type="submit">Store secret</button>
                  </form>
                </div>
              ) : null}

              <div className="config-column">
                <h3>Schedules</h3>
                {schedulesState.data?.length ? (
                  <ul className="stack-list">
                    {schedulesState.data.map((schedule) => (
                      <li key={schedule.id}>
                        <div>
                          <strong>{schedule.schedule_type}</strong>
                          <p>Next run {formatTimestamp(schedule.next_run_time)}</p>
                        </div>
                        <StatusBadge status={schedule.is_active ? "active" : "inactive"} />
                      </li>
                    ))}
                  </ul>
                ) : (
                  <EmptyState title="No schedules yet" description="Create interval or cron schedules for this package here." />
                )}
                <form className="compact-form compact-form--stacked" onSubmit={handleCreateSchedule}>
                  <select value={scheduleForm.schedule_type} onChange={(event) => setScheduleForm((prev) => ({ ...prev, schedule_type: event.target.value }))}>
                    <option value="interval">interval</option>
                    <option value="cron">cron</option>
                    <option value="at">at</option>
                  </select>
                  {scheduleForm.schedule_type === "interval" ? (
                    <input
                      min={30}
                      type="number"
                      value={scheduleForm.interval_seconds || 300}
                      onChange={(event) => setScheduleForm((prev) => ({ ...prev, interval_seconds: Number(event.target.value) }))}
                    />
                  ) : null}
                  {scheduleForm.schedule_type === "cron" ? (
                    <input
                      placeholder="*/15 * * * *"
                      value={scheduleForm.cron_expression || ""}
                      onChange={(event) => setScheduleForm((prev) => ({ ...prev, cron_expression: event.target.value }))}
                    />
                  ) : null}
                  {scheduleForm.schedule_type === "at" ? (
                    <input
                      type="datetime-local"
                      value={scheduleForm.timestamp || ""}
                      onChange={(event) => setScheduleForm((prev) => ({ ...prev, timestamp: event.target.value }))}
                    />
                  ) : null}
                  <button className="button" type="submit" disabled={isPackageOnHold}>Create schedule</button>
                </form>
              </div>
            </div>

            <Tabs
              tabs={[
                {
                  id: "runs",
                  label: "Runs",
                  content: runsState.data?.length ? (
                    <div className="table-wrap">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Run</th>
                            <th>Status</th>
                            <th>Mode</th>
                            <th>Started</th>
                            <th>Error</th>
                            <th>Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {runsState.data.slice(0, 8).map((run) => (
                            <tr className={run.id === selectedRunId ? "selected-row" : ""} key={run.id}>
                              <td>#{run.id}</td>
                              <td><StatusBadge status={run.status} /></td>
                              <td>{run.runtime_mode || "batch"}</td>
                              <td>{formatTimestamp(run.started_at)}</td>
                              <td>{run.error || "-"}</td>
                              <td>
                                <div className="table-actions">
                                  <button
                                    className="button button--small"
                                    onClick={() => {
                                      setSelectedRunId(run.id);
                                      setRunDrilldownView("events");
                                    }}
                                    type="button"
                                  >
                                    Events
                                  </button>
                                  <button
                                    className="button button--small"
                                    onClick={() => {
                                      setSelectedRunId(run.id);
                                      setRunDrilldownView("logs");
                                    }}
                                    type="button"
                                  >
                                    Logs
                                  </button>
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <EmptyState title="No runs for this package" description="Trigger a run from the Run now button to populate run history." />
                  ),
                },
                {
                  id: "events",
                  label: "Events",
                  content: selectedRun ? (
                    <div>
                      <div className="page-state-subtitle">
                        Showing events for run #{selectedRun.id}
                      </div>
                      {runEventsState.data?.length ? (
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
                              {runEventsState.data.map((event) => (
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
                        <EmptyState title="No events for selected run" description="Select a run from the Runs tab to view its events." />
                      )}
                    </div>
                  ) : (
                    <EmptyState title="Select a run first" description="Go to the Runs tab and click Events on a run to view its events here." />
                  ),
                },
                {
                  id: "logs",
                  label: "Logs",
                  content: selectedRun ? (
                    <div>
                      <div className="page-state-subtitle">
                        Showing logs for run #{selectedRun.id}
                      </div>
                      {runLogsState.data?.length ? (
                        <textarea
                          className="log-shell-textarea"
                          readOnly
                          value={runLogsState.data
                            .map(
                              (log) => `${formatTimestamp(log.ts)} ${log.stream.toUpperCase()} ${log.level.toUpperCase()} | ${log.line}`,
                            )
                            .join("\n")}
                        />
                      ) : (
                        <EmptyState title="No logs for selected run" description="Select a run from the Runs tab to view its logs here." />
                      )}
                    </div>
                  ) : (
                    <EmptyState title="Select a run first" description="Go to the Runs tab and click Logs on a run to view its logs here." />
                  ),
                },
              ]}
              activeTabId={runDrilldownView}
              onTabChange={(tabId) => setRunDrilldownView(tabId as RunDrilldownView)}
            />
          </>
        ) : (
          <EmptyState title="Select a package" description="Choose a package from the catalog to view its current state and perform package-specific actions." />
        )}
        {feedback ? <p className="inline-feedback">{feedback}</p> : null}
      </SectionCard>
    </div>
  );
}