# FastAPI Daemon Agent

Example daemon package that runs a FastAPI application and exposes it to the host.

## What this demonstrates

- `runtime_mode: "daemon"` long-running process
- FastAPI app listening on `0.0.0.0`
- Manifest `expose.port` so platform maps container port to a host port
- Optional `expose.host_port` for fixed host-port binding
- Health checks via `/health`

## Files

- `manifest.json` daemon and exposure configuration
- `src/agent.py` FastAPI application entrypoint
- `requirements.txt` Python dependencies

## Key manifest settings

```json
{
  "runtime_mode": "daemon",
  "health_check": {
    "type": "http",
    "path": "/health",
    "port": 8000
  },
  "expose": {
    "port": 8000,
    "host_port": 18000,
    "health_check_path": "/health"
  }
}
```

`expose.port` tells the worker to publish container port `8000`.

`expose.host_port` is optional:
- If set (for example `18000`), host mapping is fixed to `localhost:18000`.
- If omitted, Docker assigns a random host port dynamically.

## Deploy and run

1. Zip package

```bash
cd examples/fastapi-daemon-agent
zip -r fastapi-daemon-agent.zip .
```

2. Upload package

```bash
curl -X POST \
  -H "Authorization: Bearer $AGENTFLOW_API_TOKEN" \
  -F "zip_file=@fastapi-daemon-agent.zip" \
  http://localhost:8080/upload-package
```

3. Start daemon

```bash
curl -X POST \
  -H "Authorization: Bearer $AGENTFLOW_API_TOKEN" \
  http://localhost:8080/packages/<PACKAGE_ID>/daemon/start
```

4. Get mapped endpoint URL

```bash
curl -H "Authorization: Bearer $AGENTFLOW_API_TOKEN" \
  http://localhost:8080/packages/<PACKAGE_ID>/daemon/endpoint
```

Use returned host URL to call API routes from outside the container:

- `GET /`
- `GET /health`
- `GET /api/ping`

Example:

```bash
curl http://localhost:<EXPOSED_PORT>/api/ping
```
