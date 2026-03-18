# 🚀 CrucibleAgentPlatform

```
 ██████╗ █████╗ ███╗   ██╗ ██████╗ ██╗   ██╗███╗   ███╗
██╔════╝██╔══██╗████╗  ██║██╔════╝╚██╗ ██╔╝████╗ ████║
██║     ███████║██╔██╗ ██║██║      ╚████╔╝ ██╔████╔██║
██║     ██╔══██║██║╚██╗██║██║       ╚██╔╝  ██║╚██╔╝██║
╚██████╗██║  ██║██║ ╚████║╚██████╗   ██║   ██║ ╚═╝ ██║
 ╚═════╝╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝   ╚═╝   ╚═╝     ╚═╝
 
    Secure Agent Deployment & Execution Platform
```

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

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI REST API                        │
│         (Agent Mgmt, Run Orchestration, Secrets)             │
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
```

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
| `DAEMON_API_BASE_URL` | URL | `http://host.docker.internal:8000` | API URL accessible from daemon containers |

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
# All tests
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

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -am 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

### Code Standards
- Follow PEP 8 style guide
- Add type hints to all functions
- Include docstrings
- Write tests for new features
- Update documentation

---

## 📞 Support & Contact

- **Issue Tracker**: [GitHub Issues](https://github.com/your-org/crucibleaiagents/issues)
- **Documentation**: [Docs](./docs)
- **Examples**: [Example Agents](./examples)

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🎓 Learn More

- [Worker Runbook](docs/worker-runbook.md) - Operational guide
- [Agent Development Guide](docs/agent-development.md) - Build agents
- [API Documentation](docs/api.md) - API reference
- [Security Guide](docs/security.md) - Security best practices

---

**Built with ❤️ for the AI agent community**
