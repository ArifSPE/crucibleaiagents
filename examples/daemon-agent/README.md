# Daemon Agent Example

This example demonstrates how to build an agent that runs in **daemon mode** - a long-running background process with continuous operation and health monitoring.

## Features

- **HTTP Health Check Server**: Responds to periodic health checks at `/health` endpoint
- **Continuous Polling Loop**: Simulates event polling with configurable interval
- **Uptime Tracking**: Reports uptime and work count in health responses
- **Graceful Shutdown**: Handles `SIGTERM` for clean termination
- **Standard Library Only**: No external dependencies required
- **Auto-Start**: Automatically restart daemon on platform startup when enabled

## Runtime Backends

Daemon mode supports two execution backends:

- **Container backend**: the `worker_container` service runs the daemon in Docker and monitors health.
- **Local backend**: the host-side local worker runs the daemon as a managed subprocess.

There are currently no dedicated daemon start or stop REST endpoints. Daemon packages use the same package registration and run creation flow as batch packages, with daemon behavior controlled by manifest fields such as `runtime_mode`, `daemon_auto_start`, `health_check`, and `restart_policy`.

## Deployment

### As Batch Agent (one-time execution)
```bash
curl -X POST http://localhost:8080/runs \
  -H "Content-Type: application/json" \
  -d '{"package_id": <ID>}'
```

### As Daemon Agent (long-running)
```bash
# 1. Register package metadata
curl -X POST http://localhost:8080/packages/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "daemon-polling-agent",
    "version": "1.0.0",
    "language": "python",
    "entrypoint": "src/agent.py",
    "deployment": "container",
    "runtime_mode": "daemon",
    "daemon_auto_start": true,
    "restart_policy": "on-failure",
    "exposed_port": 5000
  }'

# 2. Place the built zip where the watcher can process it
cp daemon-agent.zip ../../package/incoming/

# 3. Create a run for the daemon package
curl -X POST http://localhost:8080/runs \
  -H "Content-Type: application/json" \
  -d '{"package_id": <ID>}'
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DAEMON_PORT` | 5000 | Port for health check HTTP server |
| `POLL_INTERVAL` | 10 | Seconds between polling cycles |
| `LOG_LEVEL` | INFO | Logging level (ERROR, INFO, DEBUG) |

### Health Check Endpoint

The agent exposes an HTTP health check endpoint for monitoring:

```bash
curl http://localhost:5000/health
```

Response:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:45.123456",
  "uptime_seconds": 3600,
  "polls_processed": 360
}
```

## Manifest Fields

Key daemon-specific fields in `manifest.json`:

```json
{
  "runtime_mode": "daemon",
  "daemon_auto_start": true,
  "health_check": {
    "type": "http",
    "path": "/health",
    "port": 5000,
    "interval_seconds": 30,
    "timeout_seconds": 5
  },
  "restart_policy": "on-failure",
  "exposed_port": 5000
}
```

### daemon_auto_start Field

- **true**: The platform will enqueue the daemon automatically during startup if it is not already queued or running.
- **false**: The daemon runs only when you explicitly create a run for the package.

## Restart Policies

- **never**: Container exits permanently
- **on-failure**: Automatically restart if exit code != 0
- **always**: Restart regardless of exit code (rare use case)

## Health Check Types

- **http**: GET request to HTTP endpoint
- **tcp**: TCP socket connectivity check
- **exec**: Execute shell command (exit code 0 = healthy)

## Example Usage

### 1. Package the example
```bash
cd examples/daemon-agent
zip -r daemon-agent.zip manifest.json src/ README.md
```

### 2. Register metadata and make the bundle available to the watcher
```bash
curl -X POST http://localhost:8080/packages/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "daemon-polling-agent",
    "version": "1.0.0",
    "description": "Example daemon agent that continuously polls for events",
    "language": "python",
    "entrypoint": "src/agent.py",
    "filename": "daemon-agent.zip",
    "deployment": "container",
    "runtime_mode": "daemon",
    "daemon_auto_start": true,
    "restart_policy": "on-failure",
    "exposed_port": 5000
  }'

cp daemon-agent.zip ../../package/incoming/
```

### 3. Create and inspect the run
```bash
curl -X POST http://localhost:8080/runs \
  -H "Content-Type: application/json" \
  -d '{"package_id": <PACKAGE_ID>}'

curl http://localhost:8080/runs/<RUN_ID>
curl http://localhost:8080/runs/<RUN_ID>/logs
curl http://localhost:8080/runs/<RUN_ID>/events
```

## What Happens with Auto-Start

1. **Platform starts** and loads packages marked with `daemon_auto_start=true`.
2. **Queued daemon runs are created** when the package is eligible and not already active.
3. **The selected worker backend picks up the run** and starts the daemon.
4. **The monitor loop performs health checks** and applies the configured restart policy if the daemon exits unexpectedly.

## What Happens in Daemon Mode

1. **Run creation** creates a run with `runtime_mode='daemon'`.
2. **Worker execution** starts the daemon in the selected backend.
3. **Monitoring** polls container or process health and records events.
4. **Restart handling** applies the configured `restart_policy` if the daemon exits.

## Local Non-Docker Daemon Mode

Use this mode when you want the host-side local worker to execute the daemon without Docker-backed agent containers.

```bash
./scripts/start.sh --daemon --local-worker
cd examples/daemon-agent
zip -r daemon-agent.zip manifest.json src/ README.md
cp daemon-agent.zip ../../package/incoming/
```

Then create a run through the normal runs API and inspect it:

```bash
curl -X POST http://localhost:8080/runs \
  -H "Content-Type: application/json" \
  -d '{"package_id": <PACKAGE_ID>}'

curl http://localhost:8080/runs/<RUN_ID>
```

In local mode, the daemon health endpoint should be reachable from the host on the configured port:

```bash
curl -s http://localhost:5000/health
```

## Key Differences from Batch Mode

| Aspect | Batch | Daemon |
|--------|-------|--------|
| Execution | Blocking | Non-blocking |
| Duration | Seconds/minutes | Hours/days/indefinite |
| Return | Wait for completion | Immediate with run_id |
| Health | No checks | Periodic health checks |
| Restart | Never | Configurable policy |
| Stop | Automatic on exit | Manual or on crash |
| Auto-Start | No | Configurable via manifest |

## Testing Locally

```bash
# Make agent executable
chmod +x src/agent.py

# Run directly (without Docker)
python src/agent.py

# In another terminal, test health endpoint
curl -s http://localhost:5000/health | jq .
```

## Production Considerations

- **Resource Limits**: Set CPU and memory limits in Docker run command
- **Logging**: Ensure adequate storage for long-running agents
- **Monitoring**: Set up alerts based on health check timeout
- **Graceful Shutdown**: Handle SIGTERM to clean up resources
- **State Persistence**: Store state externally if restart causes issues
- **Auto-Start Safety**: Verify daemon works correctly before enabling auto-start
  - Start manually first to test
  - Enable auto-start only after validation
  - Monitor restart count to detect crash loops
