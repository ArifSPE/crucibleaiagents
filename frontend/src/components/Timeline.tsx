import type { RunEvent } from "../types/api";
import { formatTimestamp, safeJson } from "../utils/format";

interface TimelineProps {
  events: RunEvent[];
}

export function Timeline({ events }: TimelineProps) {
  return (
    <div className="timeline">
      {events.map((event) => (
        <article className="timeline__item" key={event.id}>
          <div className="timeline__meta">
            <strong>{event.type}</strong>
            <span>{formatTimestamp(event.ts)}</span>
          </div>
          <p>{event.message || "No event summary provided."}</p>
          {event.payload_jason ? <pre>{safeJson(event.payload_jason)}</pre> : null}
        </article>
      ))}
      {!events.length ? <div className="timeline__placeholder">No audit events recorded yet.</div> : null}
    </div>
  );
}