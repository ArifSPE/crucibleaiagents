#!/bin/bash
#
# Deploy script for Tools Demo Agent
# 
# Usage:
#   ./deploy.sh              # Deploy agent
#   ./deploy.sh execute      # Deploy and execute
#   ./deploy.sh logs         # Deploy, execute, and show logs
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_ID="tools-demo"
API_BASE="${API_BASE:-http://localhost:8080}"

echo "=================================="
echo "Tools Demo Agent Deployment"
echo "=================================="
echo ""

# Step 1: Package agent
echo "[1/3] Packaging agent..."
cd "$SCRIPT_DIR"
rm -f tools-demo.zip
zip -q -r tools-demo.zip manifest.json src/ requirements.txt
echo "✓ Created tools-demo.zip"
echo ""

# Step 2: Upload agent
echo "[2/3] Uploading to platform..."
response=$(curl -s -X POST "$API_BASE/agents/upload" \
  -F "file=@tools-demo.zip" \
  -F "agent_id=$AGENT_ID")

if echo "$response" | grep -q "success\|uploaded"; then
  echo "✓ Agent uploaded successfully"
else
  echo "✗ Upload failed:"
  echo "$response"
  exit 1
fi
echo ""

# Step 3: Execute if requested
if [[ "$1" == "execute" ]] || [[ "$1" == "logs" ]]; then
  echo "[3/3] Executing agent..."
  exec_response=$(curl -s -X POST "$API_BASE/agents/$AGENT_ID/execute")
  
  if echo "$exec_response" | grep -q "run_id"; then
    run_id=$(echo "$exec_response" | grep -o '"run_id":"[^"]*"' | cut -d'"' -f4)
    echo "✓ Agent execution started"
    echo "  Run ID: $run_id"
    echo ""
    
    # Show logs if requested
    if [[ "$1" == "logs" ]]; then
      echo "Waiting for execution to complete..."
      sleep 3
      
      echo ""
      echo "=================================="
      echo "Execution Logs"
      echo "=================================="
      curl -s "$API_BASE/logs/$run_id" | jq -r '.[] | "\(.timestamp) [\(.level)] \(.message)"' || \
        curl -s "$API_BASE/logs/$run_id"
    fi
  else
    echo "✗ Execution failed:"
    echo "$exec_response"
    exit 1
  fi
else
  echo "[3/3] Execution skipped (use './deploy.sh execute' to run)"
  echo ""
  echo "To execute manually:"
  echo "  curl -X POST $API_BASE/agents/$AGENT_ID/execute \\"
  echo "    -H \"Authorization: Bearer \$AGENTFLOW_API_TOKEN\""
fi

echo ""
echo "=================================="
echo "Deployment Complete!"
echo "=================================="
echo ""
echo "View agent: $API_BASE/agents/$AGENT_ID"
echo "View runs:  $API_BASE/agents/$AGENT_ID/runs"
echo ""
