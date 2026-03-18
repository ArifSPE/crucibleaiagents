# local-ts-sample-agent

A TypeScript agent configured for **local deployment** testing. Use this to verify that the local worker (`worker/local_worker.py`) is functioning correctly end-to-end.

## Key differences from `ts-sample-agent`

| Property | `ts-sample-agent` | `local-ts-sample-agent` |
|---|---|---|
| `deployment` | `container` | `local` |
| Default API URL | `http://api:8000` (Docker network) | `http://localhost:8080` (host port) |
| Schedule interval | 300 s | 120 s |
| Claimed by | `container_worker.py` | `local_worker.py` |

## Structure

```
local-ts-sample-agent/
├── manifest.json       # deployment: "local", schedule interval: 120s
├── package.json        # Node.js dependencies
├── tsconfig.json       # TypeScript compiler config
├── src/
│   ├── agent.ts        # Main entrypoint — emits platform events
│   └── platform_sdk.ts # Platform SDK defaulting to http://localhost:8080
└── README.md           # This file
```

## Deploy and test locally

### 1. Package and upload

```bash
cd examples/local-ts-sample-agent
zip -r ../../local-ts-sample-agent.zip manifest.json package.json tsconfig.json src/
cd ../..

# Upload via API (platform must be running locally)
curl -X POST http://localhost:8080/upload-package \
  -F "file=@local-ts-sample-agent.zip"
```

### 2. Start the local worker

```bash
# From repo root with venv active
source .venv/bin/activate
python -m worker.local_worker
```

### 3. Manually trigger a run

```bash
# Replace <package_id> with the ID returned by the upload
curl -X POST http://localhost:8080/runs \
  -H "Content-Type: application/json" \
  -d '{"package_id": <package_id>, "inputs": {}}'
```

### 4. Watch the scheduled run

The package is configured with a 120-second interval schedule. The local worker polls
for scheduled runs every 15 seconds (configurable via `SCHEDULER_CHECK_INTERVAL`).
After the first run completes, the next run will be enqueued automatically.

### 5. Check run logs

```bash
curl http://localhost:8080/runs/<run_id>/events
```

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `API_BASE_URL` | `http://localhost:8080` | Platform API endpoint |
| `RUN_ID` | *(set by worker)* | Current run identifier |
| `AGENTFLOW_RUNNER_API_TOKEN` | *(optional)* | Bearer token for API auth |
| `POLL_SECONDS` | `5` | Worker polling interval |
| `SCHEDULER_CHECK_INTERVAL` | `15` | Schedule check interval (seconds) |
