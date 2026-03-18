#!/bin/bash

# Deploy ReAct Ollama Agent to AgentFlow Platform

set -e

AGENT_DIR="react-ollama-agent"
PACKAGE_NAME="react-ollama-agent.zip"
API_URL="${API_URL:-http://localhost:8080}"

echo "🚀 Deploying ReAct Ollama Agent to AgentFlow Platform"
echo "=============================================="

# Step 1: Verify Ollama is running
echo ""
echo "📋 Step 1: Checking if Ollama is running..."
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "✅ Ollama is running"
    echo "Available models:"
    curl -s http://localhost:11434/api/tags | python3 -m json.tool | grep '"name"' | head -5
else
    echo "⚠️  Warning: Ollama doesn't appear to be running on localhost:11434"
    echo "   Make sure to start Ollama before running the agent:"
    echo "   ollama serve"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Step 2: Package the agent
echo ""
echo "📦 Step 2: Packaging agent..."
cd "$AGENT_DIR"
if [ -f "../$PACKAGE_NAME" ]; then
    rm "../$PACKAGE_NAME"
fi
zip -r "../$PACKAGE_NAME" . -x "*.pyc" -x "__pycache__/*" -x ".git/*" -x "*.swp"
cd ..
echo "✅ Created package: $PACKAGE_NAME"

# Step 3: Upload to platform
echo ""
echo "📤 Step 3: Uploading to AgentFlow Platform..."
UPLOAD_RESPONSE=$(curl -s -X POST "$API_URL/upload-package" \
  -F "zip_file=@$PACKAGE_NAME" \
  -F "description=ReAct Ollama Agent with tool calling and web search")

echo "$UPLOAD_RESPONSE" | python3 -m json.tool

# Extract package ID
PACKAGE_ID=$(echo "$UPLOAD_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")

if [ -z "$PACKAGE_ID" ]; then
    echo "❌ Failed to upload package"
    exit 1
fi

echo "✅ Package uploaded successfully (ID: $PACKAGE_ID)"

# Step 4: Create a test run
echo ""
echo "🧪 Step 4: Creating test run..."
RUN_RESPONSE=$(curl -s -X POST "$API_URL/runs?package_id=$PACKAGE_ID&timeout_seconds=300")
echo "$RUN_RESPONSE" | python3 -m json.tool

RUN_ID=$(echo "$RUN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")

if [ -z "$RUN_ID" ]; then
    echo "❌ Failed to create run"
    exit 1
fi

echo "✅ Run created (ID: $RUN_ID)"

# Step 5: Monitor run
echo ""
echo "👀 Step 5: Monitoring run execution..."
echo "Waiting for run to complete..."

for i in {1..60}; do
    sleep 2
    STATUS_RESPONSE=$(curl -s "$API_URL/runs/$RUN_ID")
    STATUS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "unknown")
    
    echo -n "."
    
    if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
        echo ""
        echo "Status: $STATUS"
        echo "$STATUS_RESPONSE" | python3 -m json.tool
        break
    fi
done

# Step 6: Show logs
echo ""
echo "📋 Step 6: Execution logs (last 30 lines):"
echo "=============================================="
curl -s "$API_URL/runs/$RUN_ID/logs" | tail -30

echo ""
echo ""
echo "🎉 Deployment complete!"
echo ""
echo "Next steps:"
echo "  - View full run details: curl $API_URL/runs/$RUN_ID"
echo "  - View all logs: curl $API_URL/runs/$RUN_ID/logs"
echo "  - View events: curl $API_URL/runs/$RUN_ID/events"
echo ""
echo "  - Schedule regular execution:"
echo "    curl -X POST '$API_URL/packages/$PACKAGE_ID/schedule' \\"
echo "      -H 'Content-Type: application/json' \\"
echo "      -d '{\"type\": \"interval\", \"interval_seconds\": 3600, \"timeout_seconds\": 300, \"enabled\": true}'"
echo ""
