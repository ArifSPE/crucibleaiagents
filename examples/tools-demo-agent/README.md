# Platform Tools Demo Agent

This example demonstrates the comprehensive tools framework available in AgentFlow platform for building intelligent AI bots.

## Features Demonstrated

### 1. **LLM Reasoning & Tool Selection**
```python
from platform_sdk import LLMClient

llm = LLMClient(model="llama3.1", temperature=0.7)
response = llm.chat("What should I do next?", system="You are a helpful assistant")
print(response.content)
```

### 2. **Safe Shell Command Execution**
```python
from platform_sdk import ShellExecutor

shell = ShellExecutor(
    allowed_commands=["ls", "cat", "grep", "git"],
    timeout=30
)
result = shell.run("ls -la")
print(result.stdout)
```

### 3. **HTTP Requests (Curl-like)**
```python
from platform_sdk import HTTPClient

http = HTTPClient(timeout=30)
response = http.get("https://api.github.com/repos/python/cpython")
print(response.body)
```

### 4. **Custom Tool Registry**
```python
from platform_sdk import ToolRegistry, ToolParameter

registry = ToolRegistry()

@registry.tool(
    name="calculate",
    description="Perform math calculations",
    parameters=[ToolParameter("expression", "string", "Math expression")]
)
def calculate(expression: str):
    return eval(expression)

result = registry.execute("calculate", {"expression": "2 + 2"})
```

## Security Features

All tools include security controls:
- **Command Allowlist**: Only explicitly allowed commands can run
- **Execution Timeouts**: Prevent runaway processes
- **Output Size Limits**: Prevent memory exhaustion
- **Path Restrictions**: Keep operations in safe directories
- **Audit Logging**: All tool calls are logged with telemetry

## Running the Demo

### 1. Package the Agent
```bash
cd examples/tools-demo-agent
zip -r tools-demo.zip manifest.json src/
```

### 2. Deploy via API
```bash
curl -X POST http://localhost:8080/agents/upload \
  -F "file=@tools-demo.zip" \
  -F "agent_id=tools-demo"
```

### 3. Execute the Agent
```bash
curl -X POST http://localhost:8080/agents/tools-demo/execute
```

### 4. View Logs
```bash
curl http://localhost:8080/agents/tools-demo/runs | jq '.[-1].run_id'
curl http://localhost:8080/logs/{run_id}
```

## Example Output

```
[INFO] Platform Tools Demo Agent Started
[INFO] Initializing platform tools...
[INFO] Tools initialized successfully
[INFO] Registered 2 custom tools

=== LLM Reasoning Demo ===
[INFO] LLM Response (1250ms):
Top 3 use cases for AI agents in software development:
• Automated code review and bug detection
• Documentation generation from codebases
• Test case generation and execution

=== Shell Commands Demo ===
[INFO] Directory listing (exit code: 0):
total 16
drwxr-xr-x   4 user  staff   128 Jan  1 12:00 .
drwxr-xr-x  15 user  staff   480 Jan  1 12:00 ..
-rw-r--r--   1 user  staff  1234 Jan  1 12:00 agent.py

[INFO] Working directory: /app/workspace
[INFO] ✓ Security check passed: Command 'rm' not allowed

=== HTTP Requests Demo ===
[INFO] GET request completed: 200 (450ms)
[INFO] Repository: python/cpython  
[INFO] Stars: 58234
[INFO] Language: Python

=== Custom Tools Demo ===
[INFO] Available custom tools: ['analyze_json', 'calculate']
[INFO] Calculator: {'result': 22, 'expression': '2 + 2 * 10'}
[INFO] JSON analysis: {'parsed': True, 'keys': ['status', 'data'], 'type': 'dict'}

=== Agentic Workflow Demo ===
[INFO] LLM Plan:
To complete this task, I will:
1. Get current system time with 'date'
2. Check working directory with 'pwd'
3. List files with 'ls -1' and count them
4. Analyze the collected data

[INFO] Executing plan...
[INFO] 1. System date: Mon Jan 1 12:00:00 UTC 2024
[INFO] 2. Working directory: /app/workspace
[INFO] 3. File count: 3 files
[INFO] 4. Calculation result: {'result': 6, 'expression': '3 * 2'}

[INFO] Final Summary:
The system is running at /app/workspace with 3 files present. The current
time is Mon Jan 1 12:00:00 UTC 2024. All operations completed successfully.

[INFO] Demo completed successfully!
```

## Architecture

```
┌─────────────────────────────────────────┐
│         Your Agent Code                 │
│  (Uses LLM for reasoning & decisions)   │
└───────────┬─────────────────────────────┘
            │
            │ from platform_sdk import ...
            ▼
┌─────────────────────────────────────────┐
│      Platform SDK (platform_sdk.py)     │
│  ┌─────────────────────────────────┐   │
│  │ LLMClient    - Reasoning        │   │
│  │ ShellExecutor - Commands        │   │
│  │ HTTPClient   - Web requests     │   │
│  │ ToolRegistry - Custom tools     │   │
│  └─────────────────────────────────┘   │
└───────────┬─────────────────────────────┘
            │
            │ Audit events, logs
            ▼
┌─────────────────────────────────────────┐
│       AgentFlow Platform API            │
│   (Logging, Events, Secrets, Storage)   │
└─────────────────────────────────────────┘
```

## Tool Development Best Practices

### 1. Always Use Allowlists
```python
# ✓ GOOD: Explicit allowlist
shell = ShellExecutor(allowed_commands=["ls", "cat", "grep"])

# ✗ BAD: Empty allowlist = deny all (no commands work)
shell = ShellExecutor(allowed_commands=[])
```

### 2. Set Appropriate Timeouts
```python
# Short timeout for quick operations
shell = ShellExecutor(timeout=5)

# Longer timeout for complex tasks
http = HTTPClient(timeout=120)
```

### 3. Handle Errors Gracefully
```python
try:
    result = shell.run("git log --oneline")
    if result.exit_code != 0:
        logger.warning(f"Command failed: {result.stderr}")
except TimeoutError:
    logger.error("Command took too long")
except ValueError as e:
    logger.error(f"Command not allowed: {e}")
```

### 4. Use LLM for Tool Selection
```python
# Let LLM decide which tool to use
tools_description = """
Available tools:
- shell: Run system commands
- http: Make web requests  
- calculate: Math operations
"""

response = llm.chat(
    f"{tools_description}\n\nTask: {user_task}",
    system="Choose the best tool and explain your reasoning"
)
```

## Configuration

### Environment Variables
- `LLM_MODEL`: Model name (default: `llama3.1`)
- `OLLAMA_BASE_URL`: Ollama API endpoint
- `LLM_PROVIDER_ID`: Platform LLM provider ID
- `AGENTFLOW_RUNNER_API_TOKEN`: Platform API token (auto-injected)

### Secrets
Sensitive data should be stored as platform secrets:
```json
{
  "environment": {
    "API_KEY": "{secrets.MY_API_KEY}"
  },
  "secrets": ["MY_API_KEY"]
}
```

## Extending with Custom Tools

Create domain-specific tools for your use case:

```python
registry = ToolRegistry()

@registry.tool(
    name="search_docs",
    description="Search internal documentation",
    parameters=[
        ToolParameter("query", "string", "Search query"),
        ToolParameter("limit", "integer", "Max results", required=False, default=10)
    ]
)
def search_docs(query: str, limit: int = 10):
    # Your implementation
    results = search_documentation(query, limit)
    return {"results": results}

# Use in agent
result = registry.execute("search_docs", {"query": "authentication"})
```

## Integration with LangChain/LlamaIndex

The platform tools work seamlessly with popular frameworks:

```python
from langchain.tools import tool as langchain_tool
from platform_sdk import HTTPClient

http = HTTPClient()

@langchain_tool
def web_search(query: str) -> str:
    """Search the web using HTTP requests."""
    response = http.get(f"https://api.search.com/q={query}")
    return response.body
```

## Troubleshooting

### Issue: Command not allowed
```
ValueError: Command 'rm' not allowed. Allowed commands: ls, cat, grep
```
**Solution**: Add the command to `allowed_commands` list

### Issue: LLM connection failed
```
RuntimeError: LLM invocation failed: Connection refused
```
**Solution**: Check `OLLAMA_BASE_URL` or LLM provider configuration

### Issue: Timeout errors
```
TimeoutError: Command exceeded 30s timeout
```
**Solution**: Increase timeout or optimize the command

## Related Examples

- [`react-ollama-agent/`](../react-ollama-agent/) - ReAct pattern with LangChain
- [`msteam-channel-summarizer/`](../msteam-channel-summarizer/) - Production bot example
- [`scheduled-package/`](../scheduled-package/) - Scheduled bot execution

## Support

For questions or issues:
1. Check platform logs: `curl http://localhost:8080/logs/{run_id}`
2. Review agent events: `curl http://localhost:8080/agents/{agent_id}/runs`
3. Consult platform documentation: `/docs/TOOLS.md`
