#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_ACTIVATE="$PROJECT_ROOT/.venv/bin/activate"

AGENT_NAME="local-ts-sample-agent"
AGENT_DIR="$PROJECT_ROOT/examples/local-ts-sample-agent"
ZIP_PATH="$PROJECT_ROOT/local-ts-sample-agent.zip"
API_BASE_URL="${API_BASE_URL:-http://localhost:8080}"
WORKER_SECONDS="${LOCAL_WORKER_SECONDS:-20}"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'EOF'
Usage: ./scripts/run_local_ts_sample_agent.sh

Packages and deploys examples/local-ts-sample-agent, creates one run,
starts local worker briefly, and prints run summary/log tail.

Environment variables:
  API_BASE_URL           API endpoint (default: http://localhost:8080)
  LOCAL_WORKER_SECONDS   How long to run local worker (default: 20)
EOF
  exit 0
fi

if [ ! -f "$VENV_ACTIVATE" ]; then
  echo "[ERROR] Missing virtualenv at $VENV_ACTIVATE"
  exit 1
fi

cd "$PROJECT_ROOT"
source "$VENV_ACTIVATE"
export API_BASE_URL

echo "[1/7] Packaging $AGENT_NAME"
cd "$AGENT_DIR"
zip -r "$ZIP_PATH" manifest.json package.json tsconfig.json src/ >/dev/null

cd "$PROJECT_ROOT"

echo "[2/7] Checking API health"
HEALTH_JSON="$(curl -s "$API_BASE_URL/health")"
if ! echo "$HEALTH_JSON" | grep -q '"status"'; then
  echo "[ERROR] API health check failed: $HEALTH_JSON"
  exit 1
fi

echo "[3/7] Registering package metadata"
PACKAGE_ID="$(python - <<'PY'
import json
import os
import urllib.request

project_root = os.getcwd()
api_base = os.getenv('API_BASE_URL', 'http://localhost:8080').rstrip('/')

manifest_path = os.path.join(project_root, 'examples', 'local-ts-sample-agent', 'manifest.json')
with open(manifest_path, 'r', encoding='utf-8') as f:
  manifest = json.load(f)

schedule = manifest.get('schedule', {}) if isinstance(manifest.get('schedule'), dict) else {}
payload = {
  'name': manifest.get('name', 'local-ts-sample-agent'),
  'version': manifest.get('version', '1.0.0'),
  'language': manifest.get('language', 'typescript'),
  'entrypoint': manifest.get('entrypoint', 'src/agent.ts'),
  'timeout_seconds': int(manifest.get('timeout_seconds', 120)),
  'filename': 'local-ts-sample-agent.zip',
  'deployment': manifest.get('deployment', 'local'),
  'schedule_enabled': schedule.get('enabled'),
  'schedule_type': schedule.get('type'),
  'schedule_config': {
    'interval_seconds': schedule.get('interval_seconds')
  } if schedule.get('interval_seconds') is not None else None,
}

request = urllib.request.Request(
  f"{api_base}/packages/register",
  data=json.dumps(payload).encode('utf-8'),
  headers={'Content-Type': 'application/json'},
  method='POST',
)
with urllib.request.urlopen(request, timeout=30) as response:
  body = json.loads(response.read().decode('utf-8'))

print(body['id'])
PY
)"

if [ -z "$PACKAGE_ID" ]; then
  echo "[ERROR] Could not find package id for $AGENT_NAME"
  exit 1
fi

echo "[4/7] Extracting package payload"
SAFE_NAME="local-ts-sample-agent"
TARGET_DIR="$PROJECT_ROOT/package/deployed/${SAFE_NAME}_pkg${PACKAGE_ID}"
rm -rf "$TARGET_DIR"
mkdir -p "$TARGET_DIR"
unzip -q "$ZIP_PATH" -d "$TARGET_DIR"

echo "[5/7] Creating run for package_id=$PACKAGE_ID"
RUN_JSON="$(curl -s -X POST "$API_BASE_URL/runs?package_id=$PACKAGE_ID")"
RUN_ID="$(RUN_JSON="$RUN_JSON" python - <<'PY'
import json
import os

body = json.loads(os.environ['RUN_JSON'])
print(body.get('id', ''))
PY
)"

if [ -z "$RUN_ID" ]; then
  echo "[ERROR] Failed to create run: $RUN_JSON"
  exit 1
fi

echo "[6/7] Running local worker for ${WORKER_SECONDS}s to process run_id=$RUN_ID"
POLL_SECONDS=1 SCHEDULER_CHECK_INTERVAL=5 python -m worker.local_worker &
W_PID=$!
sleep "$WORKER_SECONDS"
kill "$W_PID" 2>/dev/null || true
wait "$W_PID" 2>/dev/null || true

echo "[7/7] Reading run output"
echo "Run summary:"
python - <<PY
import os
import sys
from sqlalchemy import text

sys.path.insert(0, os.getcwd())
from api.utils.db import SessionLocal

db = SessionLocal()
run_id = int("$RUN_ID")
row = db.execute(text("SELECT id, status, exit_code, error FROM runs WHERE id = :id"), {"id": run_id}).fetchone()
print(dict(row._mapping) if row else {"id": run_id, "status": "not_found"})

logs = db.execute(text("SELECT stream, line FROM run_logs WHERE run_id = :id ORDER BY id ASC LIMIT 12"), {"id": run_id}).fetchall()
for item in logs:
    print(f"[{item.stream}] {item.line}")
db.close()
PY

echo "Done."
