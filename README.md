# 🚀 CrucibleAgentPlatform

![CRUCIUM Platform](logo.png)

A production-ready platform for deploying, managing, and executing AI agents and autonomous workflows with enterprise-grade security, observability, and operational controls.

## 📋 Overview

**CrucibleAgentPlatform** is a comprehensive agent orchestration system that provides:

- **Agent Deployment**: Deploy agents in local or containerized environments
- **Lifecycle Management**: Package registration, versioning, and dependency management
- **Execution Modes**: Batch runs, scheduled executions, and long-running daemon services
- **Multi-Deployment**: Support for local subprocess and Docker container execution
- **Security**: Built-in secrets management, encryption, and access control
- **Observability**: Comprehensive logging, audit trails, and health monitoring
- **Scalability**: Threaded worker pools, scheduler integration, and async I/O
- **REST API**: Full-featured API for agent management and run orchestration
- **MCP Integration**: Dedicated FastMCP server container with HTTP tool invocation from API

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI REST API                        │
│ (Agent Mgmt, Run Orchestration, Secrets, MCP HTTP Client)   │
└──────┬──────────────────────────────────────────────┬────────┘
  │                                              │
  │                                              │
    ┌──┴──────────┐    ┌──────────────┐    ┌────────┴──────┐
    │  Scheduler  │    │   Watcher    │    │  Secrets Mgr  │
    │ (cron-based)│    │ (filesystem) │    │ (encryption)  │
    └──────┬──────┘    └──────┬───────┘    └───────────────┘
           │                  │
           │                  ▼
    ┌──────┴──────────────────────────────────────┐
    │          PostgreSQL Database                 │
    │  (packages, runs, schedules, secrets, logs)  │
    └──────┬──────────────────────────────────────┘
           │
    ┌──────┴─────────────────────────────────────────┐
    │         Worker Service Layer                   │
    │                                               │
    │  ┌─────────────────┬─────────────────┐       │
    │  │  Container Wkr  │   Local Worker   │       │
    │  │  (Docker runs)  │  (subprocess)    │       │
    │  └─────────────────┴─────────────────┘       │
    └──────┬─────────────────────────────────────────┘
           │
       ┌───────▼───────────────┐
       │   MCP Server          │
       │ (FastMCP over HTTP)   │
       └───────┬───────────────┘
          │
          ▼
        ┌───────────────┐
        │ MCP Tools     │
        │ LangGraph/LC  │
        └───────────────┘

  
           
  ┌────────┴─────────────────┬──────────────┐
  │                           │              │
  ▼                           ▼              ▼
┌─────────────────┐    ┌────────────┐  ┌─────────┐
│  Docker Runner  │    │  Daemon    │  │ Logging │
│  Containers     │    │  Monitors  │  │ & Audit │
└─────────────────┘    └────────────┘  └─────────┘
```

## 🚦 Quick Start

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- PostgreSQL 16
- 4GB RAM minimum

### Installation

```bash
# Clone repository
git clone <repository-url>
cd crucibleaiagents

# Create Python virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment (see Environment Variables section)
cp .env.example .env
# Edit .env with your configuration

# Start platform
./scripts/start.sh

# Verify health
curl http://localhost:8080/health

# Run API tests
./scripts/run_tests.sh --api -q
```

### MCP Server Integration

The platform includes a dedicated `mcp_server` service (FastMCP) running in a
separate container. The API acts as an MCP HTTP client and forwards tool calls
to the MCP endpoint.

Dependency note:

- The MCP container installs dependencies from `mcp_server/requirements.txt`.
- This is intentionally isolated from the root `requirements.txt` to avoid
  version conflicts between API pins and FastMCP/httpx/fastapi requirements.
- MCP dependencies are prebuilt into the `mcp_server` image (via `mcp_server/Dockerfile`),
  so service restarts do not re-install packages each time.
- If needed, tune startup wait with `MCP_HEALTH_TIMEOUT_SECONDS` (default 240) when
  starting with `./scripts/start.sh`.

Default MCP configuration:

- `MCP_SERVER_URL=http://mcp_server:9001/mcp`
- `MCP_CLIENT_TIMEOUT_SECONDS=20`
- `MCP_SERVER_PATH=/mcp`
- `MCP_ENABLED_TOOLS=` (comma-separated allowlist)
- `MCP_DISABLED_TOOLS=` (comma-separated denylist)
- `MCP_ALLOWED_WEB_HOSTS=` (comma-separated host allowlist for `web_service_call`)
- `MCP_WEB_REQUEST_TIMEOUT_SECONDS=10`
- `TAVILY_API_KEY=` (required for `tavily_search`)

API endpoints:

- `GET /mcp/health`: verify API-to-MCP connectivity
- `GET /mcp/tools`: list tools exposed by MCP server
- `POST /mcp/tools/{tool_name}/invoke`: invoke a tool over HTTP

Example calls:

```bash
# List tools registered by the MCP server
curl http://localhost:8080/mcp/tools

# Invoke ping tool
curl -X POST http://localhost:8080/mcp/tools/ping/invoke \
  -H "Content-Type: application/json" \
  -d '{"arguments": {"message": "hello"}}'

# Add numbers
curl -X POST http://localhost:8080/mcp/tools/add/invoke \
  -H "Content-Type: application/json" \
  -d '{"arguments": {"a": 10, "b": 5}}'

# Substract numbers (tool name intentionally matches this spelling)
curl -X POST http://localhost:8080/mcp/tools/substract/invoke \
  -H "Content-Type: application/json" \
  -d '{"arguments": {"a": 10, "b": 5}}'

# Tavily search (requires TAVILY_API_KEY)
curl -X POST http://localhost:8080/mcp/tools/tavily_search/invoke \
  -H "Content-Type: application/json" \
  -d '{"arguments": {"query": "latest model context protocol updates", "max_results": 3}}'

# Safe web service GET call (host must be in MCP_ALLOWED_WEB_HOSTS when configured)
curl -X POST http://localhost:8080/mcp/tools/web_service_call/invoke \
  -H "Content-Type: application/json" \
  -d '{"arguments": {"url": "https://example.com"}}'
```

#### Registering New MCP Tools

MCP tools are plugin-based and auto-discovered from `mcp_server/tools/**`.

1. Add a new module under `mcp_server/tools/` (for example: `mcp_server/tools/core/my_tool.py`).
2. Export one or more `MCPToolSpec` entries via a module-level `TOOL_SPECS` list.
3. Implement each tool's `register(mcp: FastMCP)` callback and decorate functions with `@mcp.tool`.
4. Restart `mcp_server`; discovery and registration happen automatically at startup.

Registration policy:

- `MCP_ENABLED_TOOLS`: if set, only listed tools are registered.
- `MCP_DISABLED_TOOLS`: listed tools are always skipped.

This model keeps server bootstrap stable while allowing safe, incremental tool additions.

### Deploy Your First Agent

```bash
# 1. Package agent
zip -r my-agent.zip manifest.json src/

# 2. Upload to platform
curl -X POST -F "file=@my-agent.zip" http://localhost:8080/packages

# 3. Create run
curl -X POST http://localhost:8080/runs?package_id=1

# 4. Monitor execution
curl http://localhost:8080/runs/1
```

---

## 📦 Agent Deployment Process

### Package Structure

Every agent deployment consists of:

1. **manifest.json** - Agent metadata and configuration
2. **Source Code** - Agent implementation (Python/TypeScript/Node.js)
3. **Dependencies** - requirements.txt, package.json, etc.

```
my-agent/
├── manifest.json          # Agent metadata
├── src/
│   └── agent.py          # Entry point specified in manifest
├── requirements.txt      # Python dependencies
└── README.md            # Documentation
```

### Manifest.json Configuration

The manifest defines how your agent runs on the platform.

#### Minimal Required Fields

```json
{
  "name": "my-agent",
  "version": "1.0.0",
  "language": "python",
  "entrypoint": "src/agent.py"
}
```

#### Complete Configuration Example

```json
{
  "name": "my-agent",
  "version": "1.0.0",
  "description": "My custom agent",
  "language": "python",
  "entrypoint": "src/agent.py",
  "timeout_seconds": 300,
  "deployment": "container",
  "runtime_mode": "batch",
  "environment": {
    "LOG_LEVEL": "INFO",
    "API_KEY": "{secrets.MY_API_KEY}"
  },
  "schedule": {
    "type": "interval",
    "interval_seconds": 3600,
    "enabled": true
  }
}
```

#### Manifest Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✓ | Unique agent identifier |
| `version` | string | ✓ | Semantic version (e.g., 1.0.0) |
| `language` | string | ✓ | `python`, `typescript`, or `nodejs` |
| `entrypoint` | string | ✓ | Relative path to entry file (e.g., src/agent.py) |
| `description` | string | — | Human-readable description |
| `timeout_seconds` | int | — | Execution timeout (10-3600, default: 300) |
| `deployment` | string | — | `local` (default) or `container` |
| `runtime_mode` | string | — | `batch` (default), `scheduled`, or `daemon` |
| `auto_start` | boolean | — | Auto-start daemon on platform boot |
| `environment` | object | — | Environment variables (use `{secrets.KEY}` for secrets) |
| `schedule` | object | — | Schedule config for scheduled mode |
| `health_check` | object | — | Health check config for daemons (HTTP) |
| `expose` | object | — | Port exposure config for daemons |
| `restart_policy` | string | — | `on-failure` or `always` (for daemons) |

### Deployment Modes & Examples

The platform includes reference implementations in the `examples/` directory:

#### 1. Local Batch Agent
**Best for**: Development, testing, lightweight tasks

[examples/local-ts-sample-agent](examples/local-ts-sample-agent)
```json
{
  "name": "local-ts-sample-agent",
  "version": "1.0.0",
  "language": "typescript",
  "entrypoint": "src/agent.ts",
  "timeout_seconds": 120,
  "deployment": "local"
}
```

**Deploy:**
```bash
cd examples/local-ts-sample-agent
zip -r ../local-ts-sample-agent.zip manifest.json src/ requirements.txt
curl -X POST -F "file=@../local-ts-sample-agent.zip" http://localhost:8080/packages
```

#### 2. Scheduled Agent
**Best for**: Periodic tasks (data collection, reports, cleanup)

[examples/sleep-test-agent](examples/sleep-test-agent)
```json
{
  "name": "sleep-test-agent",
  "version": "1.0.0",
  "language": "python",
  "entrypoint": "src/agent.py",
  "timeout_seconds": 60,
  "deployment": "local",
  "schedule": {
    "type": "interval",
    "interval_seconds": 300,
    "enabled": true
  }
}
```

#### 3. Container-based Agent
**Best for**: Production workloads, resource isolation

[examples/platform-llm-agent](examples/platform-llm-agent)
```json
{
  "name": "platform-llm-agent",
  "version": "1.0.0",
  "language": "python",
  "entrypoint": "src/agent.py",
  "timeout_seconds": 600,
  "deployment": "container",
  "environment": {
    "OPENAI_API_KEY": "{secrets.OPENAI_API_KEY}",
    "MODEL_NAME": "gpt-4"
  }
}
```

#### 4. Daemon Service
**Best for**: Long-running services, APIs, monitoring

[examples/fastapi-daemon-agent](examples/fastapi-daemon-agent)
```json
{
  "name": "fastapi-daemon-agent",
  "version": "1.0.0",
  "language": "python",
  "entrypoint": "src/agent.py",
  "deployment": "container",
  "runtime_mode": "daemon",
  "auto_start": true,
  "timeout_seconds": 0,
  "health_check": {
    "type": "http",
    "path": "/health",
    "port": 8000,
    "interval_seconds": 30
  },
  "expose": {
    "port": 8000
  },
  "restart_policy": "on-failure"
}
```

### Step-by-Step Deployment Guide

#### Step 1: Create Agent Package Structure

```bash
mkdir my-agent
cd my-agent

# Create manifest
cat > manifest.json << 'EOF'
{
  "name": "my-agent",
  "version": "1.0.0",
  "description": "My first agent",
  "language": "python",
  "entrypoint": "src/agent.py",
  "timeout_seconds": 300,
  "deployment": "local"
}
EOF

# Create source directory
mkdir src

# Create agent implementation
cat > src/agent.py << 'EOF'
import os
import json
from datetime import datetime

if __name__ == "__main__":
    run_id = os.environ.get("RUN_ID", "unknown")
    
    result = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "message": "Hello from my first agent!",
        "status": "success"
    }
    
    print(json.dumps(result, indent=2))
EOF

# Create requirements if needed
touch requirements.txt
```

#### Step 2: Package Agent

```bash
cd my-agent
zip -r ../my-agent.zip manifest.json src/ requirements.txt
cd ..
```

#### Step 3: Register with Platform

```bash
# Upload package
curl -X POST \
  -F "file=@my-agent.zip" \
  http://localhost:8080/packages

# Returns:
# {"id": 1, "name": "my-agent", "version": "1.0.0", ...}
```

#### Step 4: Create and Monitor Run

```bash
# Create run
RUN_JSON=$(curl -s -X POST "http://localhost:8080/runs?package_id=1")
RUN_ID=$(echo "$RUN_JSON" | python -c "import sys,json; print(json.load(sys.stdin).get('id',''))")

echo "Run ID: $RUN_ID"

# Poll for completion
STATUS="pending"
while [ "$STATUS" != "completed" ] && [ "$STATUS" != "failed" ]; do
  sleep 2
  STATUS=$(curl -s http://localhost:8080/runs/$RUN_ID | python -c "import sys,json; print(json.load(sys.stdin).get('status',''))")
  echo "Status: $STATUS"
done

# Get full run details and logs
curl -s http://localhost:8080/runs/$RUN_ID | python -m json.tool
```

#### Step 5: View Logs and Results

For batch/scheduled runs:
```bash
curl -s "http://localhost:8080/logs?run_id=$RUN_ID" | python -m json.tool
```

For daemon services:
```bash
# Get daemon status
curl -s http://localhost:8080/runs/$RUN_ID

# Access daemon endpoint (if exposed)
curl http://localhost:8000
```

### Available Example Agents

Reference implementations in `examples/`:

| Example | Type | Language | Use Case |
|---------|------|----------|----------|
| [local-ts-sample-agent](examples/local-ts-sample-agent) | Batch | TypeScript | Local execution demo |
| [sleep-test-agent](examples/sleep-test-agent) | Batch | Python | Simple test agent |
| [fastapi-daemon-agent](examples/fastapi-daemon-agent) | Daemon | Python | Long-running HTTP service |
| [daemon-agent](examples/daemon-agent) | Daemon | Python | Custom daemon implementation |
| [platform-llm-agent](examples/platform-llm-agent) | Batch | Python | LLM integration example |
| [react-ollama-agent](examples/react-ollama-agent) | Batch | Python | ReAct framework with Ollama |
| [tools-demo-agent](examples/tools-demo-agent) | Batch | Python | Tool usage patterns |
| [msteam-channel-summarizer](examples/msteam-channel-summarizer) | Scheduled | Python | MS Teams integration |
| [local-automation-bot](examples/local-automation-bot) | Batch | Python | Automation workflows |

**Using Example Agents:**

```bash
# Copy example
cp -r examples/fastapi-daemon-agent my-daemon

# Make modifications if needed
# ...

# Package and publish to watcher incoming directory
cd my-daemon
zip -r ../my-daemon.zip manifest.json src/ requirements.txt

# Deployment flow (watcher-based)
# 1) Configure PACKAGE_WATCHER_BASE_DIR in .env
# 2) Drop/copy package zip into ${PACKAGE_WATCHER_BASE_DIR}/incoming
cp ../my-daemon.zip "${PACKAGE_WATCHER_BASE_DIR}/incoming/"

# In CI/CD, publish the built zip artifact to the same incoming directory
# (or mounted path) so the watcher can auto-process deployment.
```

### Secrets Management

Store sensitive data securely using the secrets API:

```bash
# Store secret
curl -X POST http://localhost:8080/secrets \
  -H "Content-Type: application/json" \
  -d '{"name": "OPENAI_API_KEY", "value": "sk-..."}'

# Reference in manifest
# "environment": {
#   "OPENAI_API_KEY": "{secrets.OPENAI_API_KEY}"
# }
```

Secrets are automatically injected at runtime. Never commit API keys or credentials to version control.

---

## 🔧 Environment Variables

### Core Platform Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `APP_NAME` | string | `CrucibleAgentPlatform` | Application name (displayed in logs/UI) |
| `ENVIRONMENT` | string | `production` | Deployment environment (`development` or `production`) |
| `LOG_LEVEL` | string | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `AGENTFLOW_LOG_LEVEL` | string | `INFO` | Legacy log level variable (alternative to `LOG_LEVEL`) |

### Database Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DATABASE_URL` | URL | — | Full PostgreSQL connection URL (computed from individual vars if not provided) |
| `DB_HOST` | string | `localhost` | PostgreSQL host |
| `DB_PORT` | int | `5432` | PostgreSQL port |
| `DB_NAME` | string | `crucibleaiagents` | Database name (env var is `POSTGRES_DB` in compose) |
| `DB_USER` | string | `admin` | Database user |
| `DB_PASSWORD` | string | `secret123` | Database password (⚠️ use secrets in production) |

### Storage & Packages

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `STORAGE_DIR` | path | `package/deployed` | Directory for deployed agent packages |
| `ARCHIVE_DIR` | path | `package/archive` | Directory for archived packages |
| `PACKAGE_WATCHER_BASE_DIR` | path | `./package` | Root directory for package watcher monitoring |
| `PACKAGE_WATCHER_INCOMING_DIR` | path | `{BASE_DIR}/incoming` | Directory for incoming packages (to be deployed) |
| `PACKAGE_WATCHER_DEPLOYED_DIR` | path | `{BASE_DIR}/deployed` | Directory for successfully deployed packages |
| `PACKAGE_WATCHER_FAILED_DIR` | path | `{BASE_DIR}/failed` | Directory for failed package deployments |
| `PACKAGE_WATCHER_ARCHIVES_DIR` | path | `{BASE_DIR}/archives` | Directory for archived package bundles |

### API Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `API_BASE_URL` | URL | `http://localhost:8000` | Public API base URL (used by workers/watcher) |
| `API_TOKEN` | string | — | API authentication token |
| `AGENTFLOW_API_TOKEN` | string | — | Legacy API token variable (fallback) |
| `CORS_ORIGINS` | CSV | `*` | Comma-separated CORS allowed origins |

### Watcher Service

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `WATCHER_POLL_INTERVAL` | int | `5` | Poll interval for package watcher (seconds) |

### Worker Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `POLL_SECONDS` | int | `5` | Primary worker polling interval (seconds) |
| `SCHEDULER_CHECK_INTERVAL` | int | `15` | Scheduled runs check interval (seconds) |
| `DAEMON_AUTOSTART_CHECK_INTERVAL` | int | `30` | Daemon auto-start check interval (seconds) |
| `DAEMON_HEALTH_CHECK_INTERVAL` | int | `30` | Daemon health check interval (seconds) |
| `MAX_CONCURRENT_RUNS` | int | `10` | Maximum concurrent local/container runs |

### Docker & Runner Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `RUNNER_IMAGE` | string | `crucibleaiagents-runner:latest` | Docker image for agent execution |
| `RUNNER_API_BASE_URL` | URL | — | API URL for runners (used inside containers) |
| `DOCKER_HOST` | URL | `tcp://docker-proxy:2375` | Docker daemon endpoint for runner execution |
| `AGENTFLOW_DOCKER_NETWORK` | string | `crucibleaiagents_default` | Docker network for worker components |
| `AGENTFLOW_DAEMON_DOCKER_NETWORK` | string | `crucibleaiagents-daemon` | Docker network for daemon container isolation |
| `WORKSPACE_HOST_PATH` | path | — | Host path mounted as workspace (for agent access) |
| `WORKSPACE_PACKAGE_HOST_PATH` | path | — | Host path for packages (for agent access) |
| `DAEMON_API_BASE_URL` | URL | `http://host.docker.internal:8080` | API URL accessible from daemon containers |

### Security

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SECRETS_ENCRYPTION_KEY` | base64 | — | Fernet key for secrets encryption (⚠️ critical for security) |

---

## 📦 Deployment Modes

### Local Deployment
Agent runs as a subprocess on the host machine.

```
Advantages:
- Fast startup (<1s)
- Direct host access
- Simple debugging
- Minimal overhead

Disadvantages:
- Host resource contention
- Limited isolation
- Single instance failure affects host
```

**Use Case**: Development, testing, lightweight automation.

### Container Deployment
Agent runs in a Docker container via runner service.

```
Advantages:
- Process isolation
- Resource limits
- Easy scaling
- Reproducible environment

Disadvantages:
- Startup overhead (~2-5s)
- Resource overhead per container
- Requires Docker daemon

How to deploy:
1. Set `deployment: "container"` in agent manifest
2. Worker spawns Docker containers via runner image
3. Daemon monitor tracks container health
```

**Use Case**: Production workloads, untrusted agents, resource isolation.

---

## 🎯 Execution Modes

### Batch Runs
Execute once, exit on completion.

```bash
curl -X POST http://localhost:8080/runs?package_id=1
```

### Scheduled Runs
Execute on cron schedule.

```bash
# Create schedule
curl -X POST http://localhost:8080/schedules \
  -d '{"package_id": 1, "cron": "0 */6 * * *"}'
```

### Daemon Services
Long-running services with auto-restart.

```yaml
# In agent manifest.json
"runtime_mode": "daemon",
"deamon_auto_restart": true,
"expoded_port": 8000
```

---

## 📝 Operational Commands

### View Logs
```bash
# All service logs
./scripts/logs.sh all

# Service-specific logs
./scripts/logs.sh api
./scripts/logs.sh worker
./scripts/logs.sh watcher
./scripts/logs.sh runner
./scripts/logs.sh local_worker
```

### Start/Stop Platform
```bash
# Start with local worker
./scripts/start.sh --local-worker

# Stop all services
./scripts/stop.sh

# Restart services
./scripts/stop.sh && ./scripts/start.sh
```

### Health Check
```bash
# API health
curl http://localhost:8080/health

# Database connectivity
curl http://localhost:8080/packages

# Check running services
docker-compose ps
```

---

## 🔐 Security Best Practices

1. **Secrets Management**
   - Store sensitive data in secrets, not environment variables
   - Use strong `SECRETS_ENCRYPTION_KEY` (32-byte base64)
   - Rotate keys regularly

2. **Access Control**
   - Authenticate all API requests with `API_TOKEN`
   - Restrict network access to API ports
   - Use HTTPS in production

3. **Container Isolation**
   - Run agents in isolated Docker networks
   - Limit container resource usage
   - Use read-only filesystems where possible
   - Mount only necessary host paths

4. **Logging & Audit**
   - Enable comprehensive logging (`LOG_LEVEL=INFO` minimum)
   - Store audit logs separately
   - Monitor for suspicious activity
   - Enable security event logging in production

---

## 🛠️ Development Guide

### Project Structure
```
crucibleaiagents/
├── api/                    # FastAPI REST server
│   ├── main.py            # App entrypoint
│   ├── routers/           # API endpoints
│   ├── services/          # Business logic
│   ├── schemas/           # Request/response models
│   ├── utils/             # Utilities (DB, logging, secrets)
│   └── tests/             # Test suite
├── worker/                # Execution workers
│   ├── container_worker.py  # Docker execution loop
│   ├── local_worker.py      # Subprocess execution loop
│   ├── worker.py            # Shared run execution logic
│   ├── daemon_manager.py    # Daemon container management
│   ├── daemon_monitor.py    # Daemon health checks
│   └── scheduler.py         # Cron schedule handler
├── watcher/               # Package filesystem watcher
├── runner/                # Agent execution container image
├── scripts/               # Operational scripts
├── examples/              # Sample agents
└── docs/                  # Documentation
```

### Running Tests
```bash
# API tests (recommended wrapper)
./scripts/run_tests.sh --api -q

# All configured tests
./scripts/run_tests.sh --all

# Specific test module
./scripts/run_tests.sh --file api/tests/test_runs.py

# Raw pytest (direct)
pytest api/tests/ -v

# Specific test module
pytest api/tests/test_runs.py -v

# With coverage
pytest api/tests/ --cov=api --cov-report=html
```

### Local Development Workflow
```bash
# 1. Activate venv
source .venv/bin/activate

# 2. Set ENVIRONMENT=development (enables auto-reload)
export ENVIRONMENT=development

# 3. Start platform
./scripts/start.sh --daemon --local-worker

# 4. Develop & test
# Changes auto-reload in API and workers

# 5. View logs
./scripts/logs.sh all

# 6. Stop when done
./scripts/stop.sh
```

---

## 📖 API Endpoints

### Packages
- `POST /packages` - Register agent package
- `GET /packages` - List all packages
- `GET /packages/{package_id}` - Get package details
- `DELETE /packages/{package_id}` - Deregister package

### Runs
- `POST /runs?package_id={id}` - Create run
- `GET /runs` - List all runs
- `GET /runs/{run_id}` - Get run status & logs
- `DELETE /runs/{run_id}` - Cancel run

### Schedules
- `POST /schedules` - Create cron schedule
- `GET /schedules` - List schedules
- `DELETE /schedules/{schedule_id}` - Remove schedule

### Secrets
- `POST /secrets` - Store encrypted secret
- `GET /secrets` - List secret names
- `DELETE /secrets/{name}` - Delete secret

### System
- `GET /health` - Health check
- `GET /llm-providers` - List LLM provider configs
- `GET /logs` - Retrieve run logs

---

## 🤝 Contributing

Contributions are welcome.

For full contributor workflow and standards, see:

- [CONTRIBUTING.md](CONTRIBUTING.md)

Quick summary:

1. Fork and create a branch (`feature/...`, `fix/...`, `docs/...`).
2. Make focused changes and follow coding standards.
3. Run relevant tests (`./scripts/run_tests.sh --api -q`).
4. Open a PR with summary, rationale, risks, and test evidence.
5. Address review comments and keep docs updated.

---

## 📞 Support & Contact

- **Issue Tracker**: [GitHub Issues](https://github.com/your-org/crucibleaiagents/issues)
- **Documentation**: [Docs](./docs)
- **Examples**: [Example Agents](./examples)

---

## 📄 License

This project is licensed under a Personal Use License - see the [LICENSE](LICENSE) file for details.

Personal use is allowed. Enterprise/commercial use and support: arif@serverlessbytes.com.

---

## 🎓 Learn More

- [Worker Runbook](docs/worker-runbook.md) - Operational guide
- [Agent Development Guide](docs/agent-development.md) - Build agents
- [API Documentation](docs/api.md) - API reference
- [Security Guide](docs/security.md) - Security best practices

---

**Built with ❤️ for the AI agent community**
