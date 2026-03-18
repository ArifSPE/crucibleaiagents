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

- **Docker backend** (`worker/worker.py`): runs daemon as detached Docker containers
- **Local backend** (`worker/worker-local.py`): runs daemon as managed local subprocesses (no Docker daemon container)

Both backends use the same API endpoints:

- `POST /packages/<ID>/daemon/start`
- `GET /packages/<ID>/daemon/status`
- `POST /packages/<ID>/daemon/stop`
- `PUT /packages/<ID>/daemon/auto-start`

## Deployment

### As Batch Agent (One-time execution)
```bash
POST /runs?package_id=<ID>
```

### As Daemon Agent (Long-running)
```bash
# Manual start
POST /packages/<ID>/daemon/start

# With auto-start enabled, daemon starts automatically on platform restart
# Set via manifest: "auto_start": true
# Or toggle via API: PUT /packages/<ID>/daemon/auto-start {"auto_start": true}
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
  "auto_start": true,
  "health_check": {
    "type": "http",
    "path": "/health",
    "port": 5000,
    "interval_seconds": 30,
    "timeout_seconds": 5
  },
  "restart_policy": "on-failure"
}
```

### auto_start Field

- **true**: Daemon automatically starts when platform (API) restarts
- **false** (default): Daemon only starts when manually triggered via API
- Can be toggled at runtime via `PUT /packages/<ID>/daemon/auto-start`

## Restart Policies

- **never**: Container exits permanently
- **on-failure**: Automatically restart if exit code != 0
- **always**: Restart regardless of exit code (rare use case)

## Health Check Types

- **http**: GET request to HTTP endpoint
- **tcp**: TCP socket connectivity check
- **exec**: Execute shell command (exit code 0 = healthy)

## Example Usage

### 1. Deploy the package with auto-start enabled
```bash
cd examples/daemon-agent
zip -r daemon-agent.zip .
curl -X POST \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "zip_file=@daemon-agent.zip" \
  http://localhost:8080/upload-package
```

### 2. Check auto-start status
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8080/packages/<PACKAGE_ID>

# Response includes "daemon_auto_start": true if set in manifest
```

### 3. Check daemon status
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8080/packages/<PACKAGE_ID>/daemon/status
```

### 4. Manually start daemon
```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8080/packages/<PACKAGE_ID>/daemon/start
```

### 5. Toggle auto-start at runtime
```bash
# Enable auto-start
curl -X PUT \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"auto_start": true}' \
  http://localhost:8080/packages/<PACKAGE_ID>/daemon/auto-start

# Disable auto-start
curl -X PUT \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"auto_start": false}' \
  http://localhost:8080/packages/<PACKAGE_ID>/daemon/auto-start
```

### 6. Stop daemon
```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8080/packages/<PACKAGE_ID>/daemon/stop
```

## What Happens with Auto-Start

1. **Platform Starts** (`docker compose up` or `startup/start-local.sh`)
   - API initializes and calls `_load_auto_start_daemons()`
   - Queries all packages with `daemon_auto_start=true`
   - Creates `Run` records (status='queued', runtime_mode='daemon') for each

2. **Worker Picks Up** (continuously polling)
   - Finds queued daemon runs
  - Routes to daemon execution path
  - Starts daemon using active backend (Docker container or local subprocess)

3. **Monitor Tracks**
  - Monitor loop polls every 30 seconds (configurable)
   - Performs health checks
   - Logs status, triggers restart if needed

4. **On Platform Restart**
   - Auto-start daemons resume automatically
   - No manual intervention needed

## What Happens in Daemon Mode

1. **Start** (POST /daemon/start or auto-start on platform startup)
   - Creates `Run` record with `runtime_mode='daemon'`
  - Worker picks it up and starts daemon process for the selected backend
  - Run returns immediately in non-blocking mode

2. **Monitor** (continuously in background)
  - Polls every 30 seconds
  - Checks process/container status
   - Performs health check endpoint (HTTP GET)
   - Logs health status to database

3. **Restart** (if configured and container exits)
   - Detects container exit code
   - Checks `restart_policy`
   - Restarts container if policy allows
   - Updates restart count in `Run.restart_count`

4. **Stop** (POST /daemon/stop)
   - Sets run status to 'stopping'
   - Sends SIGTERM to process/container
   - Waits for graceful shutdown (10s timeout)
   - Force kills if necessary

## Local Non-Docker Daemon Mode

Use this mode when running API + frontend + local worker without daemon containers.

### 1. Start local stack
```bash
export AGENTFLOW_API_TOKEN="<your_token>"
export SECRETS_ENCRYPTION_KEY="<your_key>"
cd startup
./start-local.sh
```

### 2. Deploy daemon package
```bash
cd examples/daemon-agent
zip -r daemon-agent.zip .
curl -X POST \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "zip_file=@daemon-agent.zip" \
  http://localhost:8080/upload-package
```

### 3. Start daemon
```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8080/packages/<PACKAGE_ID>/daemon/start
```

### 4. Check status
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8080/packages/<PACKAGE_ID>/daemon/status
```

Expected in local mode:

- `status: "running"`
- `container_id` is a local pseudo id like `local-pid-12345`

### 5. Verify health endpoint
In local mode, the daemon listens on host localhost directly:

```bash
curl -s http://localhost:5000/health | jq .
```

### 6. Stop daemon
```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8080/packages/<PACKAGE_ID>/daemon/stop
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
