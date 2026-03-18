# Worker Runbook

This runbook explains how to run split workers and how deployment mode maps to worker execution strategy.

## Deployment Routing Matrix

| AgentPackage.deployment | Claimed by worker | Execution mode |
|---|---|---|
| local (default) | host local worker process | Subprocess on host PC |
| container | worker_container | Docker runner container (`docker run`) |

Notes:
- Values are normalized to `local` or `container` during package registration.
- Empty or unknown deployment values are treated as `local`.

## Start With Docker Compose

Build and run core stack:

```bash
docker compose up --build db api watcher worker_container
```

Run in background:

```bash
docker compose up -d --build db api watcher worker_container
```

Stop stack:

```bash
docker compose down
```

## Required Runtime Conditions

- `worker_container` must have access to Docker daemon via `/var/run/docker.sock`.
- Runner image must exist for container deployments:

```bash
docker build -t crucibleaiagents-runner:latest ./runner
```

- Local worker must run on host OS (not in Docker):

```bash
./scripts/run_local_worker_host.sh
```

## Useful Environment Variables

- `POLL_SECONDS`: worker polling interval.
- `RUNNER_IMAGE`: runner image for container deployments (default: `crucibleaiagents-runner:latest`).
- `RUNNER_API_BASE_URL`: API URL runner uses for posting events/logs.
- `DATABASE_URL`: worker database connection string.

## Quick Validation Flow

1. Register package with `deployment=local` and create a run.
2. Verify `worker_local` picks it and run completes.
3. Register package with `deployment=container` and create a run.
4. Verify `worker_container` picks it and a Docker container is started.
5. Check run logs/events from API endpoints.

## Debug Tips

Check worker logs:

```bash
docker compose logs -f worker_local
docker compose logs -f worker_container
```

Host local worker logs are printed in the terminal where `./scripts/run_local_worker_host.sh` is running.

Check API run state:

```bash
curl -s http://localhost:8080/runs | jq
```
