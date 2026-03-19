interface StatusBadgeProps {
  status: string | null | undefined;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const normalized = (status || "unknown").toLowerCase();
  return <span className={`status-badge status-badge--${normalized}`}>{status || "unknown"}</span>;
}