# Quick Start: Deploy ReAct Ollama Agent

## Prerequisites

1. **CrucibleAgentPlatform Running**:
   ```bash
   cd /Users/arifshaikh/Development/crucibleaiagents
   ./scripts/start.sh --daemon
   ```

2. **Ollama Running Locally**:
   ```bash
   # Install Ollama from https://ollama.ai
   
   # Pull the model
   ollama pull llama3.1
   
   # Start Ollama (usually auto-starts)
   ollama serve
   
   # Verify it's running
   curl http://localhost:11434/api/tags
   ```

3. **Runner Image Built**:
   ```bash
   cd runner
   docker build -t crucibleaiagents-runner:latest .
   cd ..
   ```

## Option 1: Automated Deployment (Recommended)

Use the provided deployment script:

```bash
cd react-ollama-agent
./deploy.sh
```

This will:
1. ✅ Check if Ollama is running
2. 📦 Package the agent as a zip file
3. 📤 Register it with the platform
4. 🧪 Create a test run
5. 👀 Monitor execution
6. 📋 Show logs

## Option 2: Manual Deployment

### Step 1: Package the Agent

```bash
cd react-ollama-agent
zip -r ../react-ollama-agent.zip . -x "*.pyc" -x "__pycache__/*"
cd ..
```

### Step 2: Register with the Platform

```bash
curl -X POST "http://localhost:8080/packages/register" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "react-ollama-agent",
    "version": "1.0.0",
    "language": "python",
    "entrypoint": "src/agent.py",
    "filename": "react-ollama-agent.zip",
    "deployment": "container"
  }'

cp react-ollama-agent.zip package/incoming/
```

Response will include the `package_id`.

### Step 3: Create a Run

```bash
# Replace <PACKAGE_ID> with the ID from step 2
curl -X POST "http://localhost:8080/runs" \
  -H "Content-Type: application/json" \
  -d '{"package_id": <PACKAGE_ID>}'
```

Response will include the `run_id`.

### Step 4: Monitor Execution

```bash
# Check status
curl "http://localhost:8080/runs/<RUN_ID>"

# View logs
curl "http://localhost:8080/runs/<RUN_ID>/logs"

# View telemetry events
curl "http://localhost:8080/runs/<RUN_ID>/events"
```

### Step 5: (Optional) Schedule Regular Execution

```bash
# Run every hour
curl -X POST "http://localhost:8080/packages/<PACKAGE_ID>/schedules" \
  -H "Content-Type: application/json" \
  -d '{
    "schedule_type": "interval",
    "interval_seconds": 3600,
    "enabled": true
  }'
```

## Testing Locally (Outside Platform)

You can also test the agent locally before deploying:

```bash
# Install dependencies
cd react-ollama-agent
pip install -r requirements.txt

# Set environment variables
export TAVILY_API_KEY="your-tavily-api-key"
export OLLAMA_BASE_URL="http://localhost:11434"
export OLLAMA_MODEL="llama3.1"

# Run the agent
python src/agent.py
```

## Troubleshooting

### "Connection refused to localhost:11434"

**Problem**: Ollama is not running or not accessible.

**Solution**:
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# If not, start it
ollama serve

# Or check process
ps aux | grep ollama
```

### "Model llama3.1 not found"

**Problem**: Model hasn't been pulled.

**Solution**:
```bash
# Pull the model
ollama pull llama3.1

# Verify
ollama list
```

### Agent Can't Reach Ollama from Docker

**Problem**: Docker container can't access localhost.

**Solution**: The manifest is configured to use `http://host.docker.internal:11434` which should work on Docker Desktop (Mac/Windows). 

For Linux, you may need to use:
```bash
# Edit manifest.json
"OLLAMA_BASE_URL": "http://172.17.0.1:11434"
```

Or run Ollama in Docker on the same network:
```bash
docker run -d --network crucibleaiagents_default \
  --name ollama -v ollama:/root/.ollama \
  -p 11434:11434 ollama/ollama
  
docker exec -it ollama ollama pull llama3.1
```

### "Tavily API Error"

**Problem**: Invalid or expired API key.

**Solution**: Get a new API key from https://tavily.com and update `manifest.json`.

## Viewing Results

After the agent runs, you can view:

1. **Run Status**:
   ```bash
   curl "http://localhost:8080/runs/<RUN_ID>" | jq .
   ```

2. **Full Logs**:
   ```bash
   curl "http://localhost:8080/runs/<RUN_ID>/logs"
   ```

3. **Telemetry Events** (steps, tool calls, timing):
   ```bash
   curl "http://localhost:8080/runs/<RUN_ID>/events"
   ```

## What the Agent Does

The agent processes queries using the ReAct pattern:

1. **Receives query**: e.g., "What's the weather in Zurich? What should I wear?"
2. **LLM reasoning**: Decides to use the `search_tool`
3. **Tool execution**: Searches web for Zurich weather
4. **LLM synthesis**: Analyzes temperature from results
5. **Tool execution**: Calls `recommend_clothing` with temperature
6. **Final answer**: Combines weather info and clothing recommendation

Example output:
```
Based on my search, the weather in Zurich is currently 15°C. 
Given this temperature, I recommend wearing a light jacket or 
sweater - it's cool but not too cold.
```

## Next Steps

- Modify queries in `src/agent.py` to test different scenarios
- Add more tools to extend functionality
- Adjust `max_iterations` for more complex reasoning
- Schedule regular execution for periodic tasks
- Monitor using the CrucibleAgentPlatform API

## Package Structure

```
react-ollama-agent/
├── src/
│   └── agent.py           # Main agent code with ReAct logic
├── manifest.json          # Package metadata and configuration
├── requirements.txt       # Python dependencies
├── Dockerfile            # Container definition (optional)
├── deploy.sh             # Automated deployment script
├── README.md             # Detailed documentation
├── QUICKSTART.md         # This file
└── .gitignore           # Git ignore patterns
```

## Environment Variables

Configure in `manifest.json` or override at runtime:

- `TAVILY_API_KEY`: Tavily search API key
- `OLLAMA_BASE_URL`: Ollama server URL (default: `http://host.docker.internal:11434`)
- `OLLAMA_MODEL`: Model name (default: `llama3.1`)

## Support

For issues or questions:
- Check [README.md](README.md) for detailed documentation
- Review [ARCHITECTURE.md](../ARCHITECTURE.md) for platform details
- Check [SCHEDULER_GUIDE.md](../SCHEDULER_GUIDE.md) for scheduling help
