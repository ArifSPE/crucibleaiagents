#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COLLECTION="$ROOT_DIR/crucible-api-integration.postman_collection.json"
ENV_FILE="$ROOT_DIR/crucible-local.postman_environment.json"
REPORT_DIR="$ROOT_DIR/newman-report"
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"

mkdir -p "$REPORT_DIR"

if command -v curl >/dev/null 2>&1; then
  if ! curl --silent --show-error --fail "$BASE_URL/openapi.json" >/dev/null; then
    echo "Error: API is not reachable at $BASE_URL. Start the API first, then rerun." >&2
    exit 1
  fi
fi

if command -v newman >/dev/null 2>&1; then
  NEWMAN_CMD=(newman)
elif command -v npx >/dev/null 2>&1; then
  NEWMAN_CMD=(npx --yes newman)
else
  echo "Error: neither 'newman' nor 'npx' is available. Install Node.js or Newman." >&2
  exit 1
fi

# shellcheck disable=SC2068
${NEWMAN_CMD[@]} run "$COLLECTION" \
  --environment "$ENV_FILE" \
  --env-var "baseUrl=$BASE_URL" \
  --bail \
  --reporters cli,junit \
  --reporter-junit-export "$REPORT_DIR/newman-results.xml"

echo "Newman run completed. JUnit report: $REPORT_DIR/newman-results.xml"
