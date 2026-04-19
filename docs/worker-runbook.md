# Worker Runbook

This runbook explains how the platform routes runs to the correct worker path and how to validate local versus container execution.

## Deployment Routing Matrix

| Package deployment | Claimed by | Execution mode |
|---|---|---|
| local | local worker on the host | Subprocess execution on the host machine |
| container | worker_container | Detached Docker runner container |

Notes:
- Deployment values are normalized to local or container during package registration.
- Empty or unknown deployment values fall back to local.

## Start the Core Platform

```bash
./scripts/start.sh --daemon
```

This starts the database, MCP server, API, watcher, and container worker services.

If you also want to process local deployment runs on the host, start the local worker too:

```bash
./scripts/run_local_worker.sh start
```

## Required Runtime Conditions

- Docker Desktop or Docker Engine with Compose v2 must be running.
- The worker_container service talks to Docker through the restricted docker-proxy service.
- The runner image for container workloads is built automatically by the platform scripts when needed.

## Useful Environment Variables

- `POLL_SECONDS`: worker polling interval.
- `RUNNER_IMAGE`: runner image for container deployments.
- `RUNNER_API_BASE_URL`: API URL used inside runner containers.
- `DATABASE_URL`: worker database connection string.
- `DAEMON_HEALTH_CHECK_INTERVAL`: monitor interval for daemon health checks.

## Quick Validation Flow

1. Register a package with deployment set to local and create a run.
2. Confirm the host local worker processes it successfully.
3. Register a package with deployment set to container and create a run.
4. Confirm worker_container starts and tracks the Docker-backed run.
5. Inspect logs and events from the API.

## Debug Tips

Check container worker logs:

```bash
docker compose logs -f worker_container
```

Check local worker logs:

```bash
./scripts/run_local_worker.sh logs -f
```

Check API run state:

```bash
curl -s http://localhost:8080/runs
curl -s http://localhost:8080/runs/1/logs
curl -s http://localhost:8080/runs/1/events
```
