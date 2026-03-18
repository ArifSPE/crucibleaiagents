# Crucible AI Agents

Secure agent deployment and execution platform with API, watcher, scheduler, worker, and runner components.

## Worker Execution Modes

Workers are split by deployment mode for clear separation of concerns.

| AgentPackage.deployment | Worker service | Execution mode |
|---|---|---|
| local (default) | host local worker process | Local subprocess execution on host PC |
| container | worker_container | Docker runner container execution |

See full operational steps in [docs/worker-runbook.md](docs/worker-runbook.md).
