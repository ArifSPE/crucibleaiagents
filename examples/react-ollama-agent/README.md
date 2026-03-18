# ReAct Ollama Agent

A LangChain-based agent using the ReAct (Reasoning + Acting) pattern with Ollama LLM and tool calling.

## Features

- **ReAct Pattern**: Iterative reasoning and action steps
- **Ollama Integration**: Uses Llama 3.1 or other Ollama models
- **Tool Calling**: 
  - `search_tool`: Web search using Tavily API
  - `recommend_clothing`: Temperature-based clothing recommendations
  - `sanity_tool`: Basic health check tool
- **LangGraph State Management**: Proper message state handling
- **Platform SDK Integration**: Instrumented for telemetry collection

## Configuration

### Environment Variables

- `TAVILY_API_KEY`: API key for Tavily web search (default: included in manifest)
- `OLLAMA_BASE_URL`: Ollama server URL (default: `http://host.docker.internal:11434`)
- `OLLAMA_MODEL`: Model to use (default: `llama3.1`)

### Prerequisites

**Ollama Must Be Running Locally**:
```bash
# Install Ollama (if not installed)
# Visit: https://ollama.ai

# Pull the model
ollama pull llama3.1

# Start Ollama (usually runs automatically)
ollama serve
```

The agent connects to Ollama on your host machine using `host.docker.internal:11434` when running in Docker.

## Usage

### Upload to Platform

```bash
# Package the agent
cd react-ollama-agent
zip -r ../react-ollama-agent.zip .

# Upload via API
curl -X POST "http://localhost:8080/upload-package" \
  -F "package=@../react-ollama-agent.zip" \
  -F "description=ReAct Ollama Agent with tool calling"
```

### Run Manually

```bash
# Create a run
curl -X POST "http://localhost:8080/runs?package_id=<ID>&timeout_seconds=300"

# Check status
curl "http://localhost:8080/runs/<RUN_ID>"

# View logs
curl "http://localhost:8080/runs/<RUN_ID>/logs"

# View events
curl "http://localhost:8080/runs/<RUN_ID>/events"
```

### Schedule Execution

```bash
# Run every hour
curl -X POST "http://localhost:8080/packages/<ID>/schedule" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "interval",
    "interval_seconds": 3600,
    "timeout_seconds": 300,
    "enabled": true
  }'
```

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export TAVILY_API_KEY="your-api-key"
export OLLAMA_BASE_URL="http://localhost:11434"
export OLLAMA_MODEL="llama3.1"

# Run locally
python src/agent.py
```

## How It Works

1. **Initialization**: Agent loads Ollama LLM and binds tools
2. **Query Processing**: User query is sent to LLM with system prompt
3. **Tool Execution**: LLM decides which tools to call based on query
4. **Iteration**: Results are fed back to LLM for synthesis
5. **Response**: Final answer returned after reasoning steps

## Example Queries

The agent can handle complex queries like:
- "What's the weather in Zurich? and What should I wear today based on temperature?"
- "Search for the latest news about AI"
- "If it's 15 degrees Celsius, what should I wear?"

## Telemetry

When running on the AgentFlow platform, the agent automatically captures:
- Step execution timing (initialize_agent, process_query, run_agent)
- Tool invocations and results
- All log output
- Subprocess calls

## Troubleshooting

**"Connection refused" errors**:
- Ensure Ollama is running: `ollama list`
- Check Ollama is accessible: `curl http://localhost:11434/api/tags`
- Verify `OLLAMA_BASE_URL` is correct

**"Model not found" errors**:
- Pull the model: `ollama pull llama3.1`
- Verify available models: `ollama list`

**Tavily API errors**:
- Verify `TAVILY_API_KEY` is set correctly
- Check API quota at https://tavily.com

## Dependencies

- `langchain`: Core LangChain library
- `langchain-community`: Community integrations
- `langchain-ollama`: Ollama LLM integration
- `langgraph`: State graph for agentic workflows
- `tavily-python`: Web search API
- `pydantic`: Data validation

## License

Same as AgentFlow platform.
