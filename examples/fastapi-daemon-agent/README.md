# FastAPI Daemon Agent

Example daemon package that runs a FastAPI application and exposes it to the host.

## What this demonstrates

- `runtime_mode: "daemon"` for long-running execution
- FastAPI app listening on `0.0.0.0`
- Manifest `exposed_port` so the platform maps the daemon port to the host
- `daemon_auto_start` support for boot-time startup
- Health checks via `/health`

## Files

- `manifest.json` daemon and exposure configuration
- `src/agent.py` FastAPI application entrypoint
- `requirements.txt` Python dependencies

## Key manifest settings

```json
{
  "runtime_mode": "daemon",
  "daemon_auto_start": true,
  "health_check": {
    "type": "http",
    "path": "/health",
    "port": 8000
  },
  "exposed_port": 8000,
  "restart_policy": "on-failure"
}
```

`exposed_port` tells the platform which host port to publish for the daemon.

## Deploy and run

1. Zip package

```bash
cd examples/fastapi-daemon-agent
zip -r fastapi-daemon-agent.zip manifest.json src/ requirements.txt README.md
```

2. Register metadata and place the bundle in the watcher folder

```bash
curl -X POST http://localhost:8080/packages/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "fastapi-daemon-agent",
    "version": "1.0.0",
    "language": "python",
    "entrypoint": "src/agent.py",
    "filename": "fastapi-daemon-agent.zip",
    "deployment": "container",
    "runtime_mode": "daemon",
    "daemon_auto_start": true,
    "exposed_port": 8000,
    "restart_policy": "on-failure"
  }'

cp fastapi-daemon-agent.zip ../../package/incoming/
```

3. Create a run

```bash
curl -X POST http://localhost:8080/runs \
  -H "Content-Type: application/json" \
  -d '{"package_id": <PACKAGE_ID>}'
```

4. Access the exposed endpoint

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/ping
```
