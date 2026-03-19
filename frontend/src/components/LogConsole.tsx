import type { RunLog } from "../types/api";
import { formatTimestamp } from "../utils/format";

interface LogConsoleProps {
  logs: RunLog[];
}

export function LogConsole({ logs }: LogConsoleProps) {
  return (
    <div className="log-console">
      {logs.map((log) => (
        <div className="log-console__line" key={log.id}>
          <span className="log-console__ts">{formatTimestamp(log.ts)}</span>
          <span className={`log-console__level log-console__level--${log.level.toLowerCase()}`}>{log.level}</span>
          <span className="log-console__stream">{log.stream}</span>
          <span className="log-console__message">{log.line}</span>
        </div>
      ))}
      {!logs.length ? <div className="log-console__placeholder">No logs recorded yet.</div> : null}
    </div>
  );
}