# Platform Management Scripts

Comprehensive shell scripts for managing the crucibleaiagents Docker Compose platform.

## Quick Start

```bash
# Make all scripts executable
chmod +x scripts/*.sh

# Start the platform
./scripts/start.sh

# In another terminal, view logs
./scripts/logs.sh

# Check status
./scripts/status.sh

# Stop the platform
./scripts/stop.sh
```

## Scripts Overview

### 🚀 `manage.sh` - Interactive Platform Management Hub

Central command for all platform operations with interactive and CLI modes.

**Interactive Mode:**
```bash
./scripts/manage.sh
```

Provides menu-driven interface for:
- Start/stop/restart platform
- View logs and daemon monitor events
- Check status
- Start local worker
- **Manage local watcher** (start/stop/restart/logs)
- Shell operations (rebuild, cleanup, etc.)

**CLI Mode:**
```bash
./scripts/manage.sh start --daemon
./scripts/manage.sh status --all
./scripts/manage.sh logs api
./scripts/manage.sh logs local_watcher
./scripts/manage.sh watcher start          # Start local watcher
./scripts/manage.sh watcher logs -f        # Follow local watcher logs
./scripts/manage.sh restart worker_container
```

---

### 🔄 `run_local_watcher.sh` - Local Package Watcher Manager

Manage the local watcher process running on the host (not in Docker).

**Usage:**
```bash
./scripts/run_local_watcher.sh [COMMAND] [OPTIONS]
```

**Commands:**
- `start` - Start the local watcher process
- `stop` - Stop the local watcher process
- `status` - Check if watcher is running
- `restart` - Restart the watcher
- `logs` - Show watcher logs

**Options:**
- `-f, --follow` - Follow logs in real-time (with 'logs' command)
- `-n N` - Show last N lines (with 'logs' command, default: 50)
- `--no-color` - Disable colored output
- `-h, --help` - Show help

**Examples:**
```bash
# Start local watcher
./scripts/run_local_watcher.sh start

# Check status
./scripts/run_local_watcher.sh status

# Follow logs
./scripts/run_local_watcher.sh logs -f

# Show last 100 lines
./scripts/run_local_watcher.sh logs -n 100

# Restart
./scripts/run_local_watcher.sh restart
```

**What it does:**
1. ✅ Runs `watcher/package_watcher.py` as a background process
2. ✅ Logs output to `logs/local_watcher.log`
3. ✅ Stores PID in `.local_watcher.pid`
4. ✅ Graceful shutdown on stop (SIGTERM, then SIGKILL if needed)
5. ✅ Status checks with process inspection

---

### ⚙️ `run_local_worker.sh` - Local Worker Manager

Manage the local worker process running on the host (not in Docker).

**Usage:**
```bash
./scripts/run_local_worker.sh [COMMAND] [OPTIONS]
```

**Commands:**
- `start` - Start the local worker process
- `stop` - Stop the local worker process
- `status` - Check if worker is running
- `restart` - Restart the worker
- `logs` - Show worker logs

**Options:**
- `-f, --follow` - Follow logs in real-time (with 'logs' command)
- `-n N` - Show last N lines (with 'logs' command, default: 50)
- `--no-color` - Disable colored output
- `-h, --help` - Show help

**Examples:**
```bash
# Start local worker
./scripts/run_local_worker.sh start

# Check status
./scripts/run_local_worker.sh status

# Follow logs
./scripts/run_local_worker.sh logs -f

# Restart
./scripts/run_local_worker.sh restart
```

**What it does:**
1. ✅ Runs `worker/local_worker.py` as a background host process through `run_local_worker_host.sh`
2. ✅ Logs output to `logs/local_worker.log`
3. ✅ Stores PID in `.local_worker.pid`
4. ✅ Graceful shutdown on stop (SIGTERM, then SIGKILL if needed)
5. ✅ Status checks with process inspection

---

### 🧪 `run_tests.sh` - Test Runner

Run test suites with simple presets and pass-through pytest options.

**Usage:**
```bash
./scripts/run_tests.sh [OPTIONS] [-- PYTEST_ARGS...]
```

**Options:**
- `--api` - Run API tests (`api/tests`)
- `--all` - Run all configured tests (default)
- `--file PATH` - Run a specific test file (repeatable)
- `-k, --keyword EXPR` - Pytest keyword expression
- `-m, --marker EXPR` - Pytest marker expression
- `-q, --quiet` - Quiet output
- `-v, --verbose` - Verbose output
- `--help` - Show help

**Examples:**
```bash
# Run API tests quietly
./scripts/run_tests.sh --api -q

# Run specific files
./scripts/run_tests.sh --file api/tests/test_runs.py --file api/tests/test_secrets.py

# Run matching tests by keyword
./scripts/run_tests.sh --api -k schedule

# Forward raw pytest args
./scripts/run_tests.sh -- --maxfail=1 -x
```

---

### ▶️ `start.sh` - Start Platform

Starts all platform services in correct dependency order with health checks.

**Usage:**
```bash
./scripts/start.sh [OPTIONS]
```

**Options:**
- `--build` - Build images before starting
- `--daemon` - Run in background (default: show live logs)
- `--local-watcher` - Also start local watcher process
- `--local-worker` - Also start local worker process
- `--no-color` - Disable colored output
- `--help` - Show help

**Examples:**
```bash
# Start with live logs (Ctrl+C to detach)
./scripts/start.sh

# Build fresh images and start in background
./scripts/start.sh --build --daemon

# Start with local watcher
./scripts/start.sh --daemon --local-watcher

# Start with local worker
./scripts/start.sh --daemon --local-worker

# Just start in background
./scripts/start.sh --daemon
```

**What it does:**
1. ✅ Checks Docker and docker-compose availability
2. ✅ Loads `.env` environment variables
3. ✅ Starts `docker-proxy` (security layer)
4. ✅ Starts database with health checks
5. ✅ Starts API with health checks
6. ✅ Starts watcher, worker, and other services
7. ✅ **Optionally** starts local watcher if `--local-watcher` flag used
8. ✅ **Optionally** starts local worker if `--local-worker` flag used
9. ✅ Verifies all services are running
10. ✅ Shows live logs or runs in background

---

### ⏹️ `stop.sh` - Stop Platform

Gracefully stops platform services.

**Usage:**
```bash
./scripts/stop.sh [OPTIONS]
```

**Options:**
- `--force` - Force stop immediately (no graceful shutdown)
- `--remove` - Remove containers after stopping (keeps networks/volumes)
- `--volumes` - Also remove volumes (⚠️ DATA LOSS)
- `--no-color` - Disable colored output
- `--help` - Show help

**Examples:**
```bash
# Graceful stop, keep containers
./scripts/stop.sh

# Stop and remove containers
./scripts/stop.sh --remove

# Force stop and remove everything
./scripts/stop.sh --force --remove

# Stop and remove volumes (careful!)
./scripts/stop.sh --remove --volumes
```

**What it does:**
1. ✅ Shows running services
2. ✅ Stops local watcher if running
3. ✅ Stops local worker if running
4. ✅ Gracefully stops with 30s timeout (or immediately if --force)
5. ✅ Optionally removes containers and volumes
5. ✅ Preserves restart ability if containers kept

---

### 📊 `status.sh` - Check Platform Status

Comprehensive health and status checks.

**Usage:**
```bash
./scripts/status.sh [OPTIONS]
```

**Options:**
- `--detailed` - Show detailed container information
- `--check-api` - Verify API is responding (HTTP GET /health)
- `--check-db` - Verify database connection
- `--all` - All checks combined
- `--no-color` - Disable colored output
- `--help` - Show help

**Examples:**
```bash
# Quick overview
./scripts/status.sh

# Full health check
./scripts/status.sh --all

# Detailed status with API check
./scripts/status.sh --detailed --check-api

# Database connection check only
./scripts/status.sh --check-db
```

**What it does:**
1. ✅ Lists service statuses (running, stopped, unhealthy)
2. ✅ Shows exposed ports
3. ✅ Optionally checks API responsiveness
4. ✅ Optionally verifies database connectivity
5. ✅ Provides helpful next steps

---

### 📜 `logs.sh` - View Service Logs

Follow and view logs from any service.

**Usage:**
```bash
./scripts/logs.sh [SERVICE] [OPTIONS]
```

**Services:**
- `all` - All services (default)
- `api` - FastAPI server
- `db` - PostgreSQL database
- `watcher` - Package watcher
- `worker_container` - Container worker + daemon monitor
- `docker-proxy` - Docker socket proxy
- `runner` - Agent runner (if enabled)

**Options:**
- `-f, --follow` - Follow log output (default)
- `-n, --lines N` - Show last N lines (default: 50)
- `--no-follow` - Show and exit
- `--timestamps` - Include timestamps
- `--no-color` - Disable colored output
- `--help` - Show help

**Examples:**
```bash
# Follow all logs
./scripts/logs.sh

# Follow API logs only
./scripts/logs.sh api

# Show last 100 lines of worker logs
./scripts/logs.sh worker_container -n 100

# Show daemon monitor events
./scripts/logs.sh worker_container | grep daemon.monitor

# Show only errors
./scripts/logs.sh | grep ERROR
```

**Filtering Tips:**
```bash
# Follow daemon monitor events
./scripts/logs.sh worker_container | grep "daemon.monitor"

# Follow daemon restarts
./scripts/logs.sh | grep "restart_requested\|restart_succeeded"

# Follow health check failures
./scripts/logs.sh | grep "health_check_failed"

# Show only worker errors
./scripts/logs.sh worker_container | grep "ERROR\|FAIL\|Exception"
```

---

### 🔄 `restart.sh` - Restart Services

Restart one or all platform services.

**Usage:**
```bash
./scripts/restart.sh [SERVICE] [OPTIONS]
```

**Services:**
- `all` - All services (default)
- `api`, `db`, `watcher`, `worker_container`, `docker-proxy`, `runner`

**Options:**
- `--hard` - Force restart immediately (no graceful shutdown)
- `--graceful` - Graceful restart (default, 30s timeout)
- `--timeout N` - Custom shutdown timeout
- `--rebuild` - Rebuild image before restarting
- `--no-deps` - Don't restart dependencies
- `--no-color` - Disable colored output
- `--help` - Show help

**Examples:**
```bash
# Graceful restart all services
./scripts/restart.sh

# Restart API only
./scripts/restart.sh api

# Restart local watcher
./scripts/restart.sh local_watcher

# Force restart worker
./scripts/restart.sh worker_container --hard

# Rebuild and restart API
./scripts/restart.sh api --rebuild

# Restart database with 60s shutdown timeout
./scripts/restart.sh db --timeout 60
```

**What it does:**
1. ✅ Optionally rebuilds images
2. ✅ Stops service(s) gracefully or forcefully
3. ✅ Waits for them to be ready (API responds, DB accessible)
4. ✅ Shows updated service status

---

### 🧪 `run_local_ts_sample_agent.sh` - One-command Local TS Sample Validation

Packages, registers, deploys, runs, and validates the local TypeScript sample
agent against `local_worker`.

**Usage:**
```bash
./scripts/run_local_ts_sample_agent.sh
```

**Options:**
```bash
./scripts/run_local_ts_sample_agent.sh --help
```

**Environment variables:**
- `API_BASE_URL` (default: `http://localhost:8080`)
- `LOCAL_WORKER_SECONDS` (default: `20`)

**What it does:**
1. ✅ Creates `local-ts-sample-agent.zip` from `examples/local-ts-sample-agent`
2. ✅ Registers package metadata via `/packages/register`
3. ✅ Extracts package to `package/deployed/<name>_pkg<ID>`
4. ✅ Creates one run via `/runs?package_id=...`
5. ✅ Runs `worker/local_worker.py` briefly to process the run
6. ✅ Prints run status and recent logs

---

## Common Workflows

### Morning Startup
```bash
# Start platform with local watcher
./scripts/start.sh --local-watcher

# In another terminal, check status
./scripts/status.sh --all
```

### Development - Continuous Logs
```bash
# Terminal 1: platform operations
./scripts/start.sh --daemon --local-watcher

# Terminal 2: watch all logs
./scripts/logs.sh -f

# Terminal 3: watch worker/daemon events
./scripts/logs.sh worker_container | grep daemon

# Terminal 4: watch local watcher
./scripts/logs.sh local_watcher -f

# Terminal 5: local worker
./scripts/run_local_worker.sh start
```

### Daemon Package Testing
```bash
# Start platform with local watcher
./scripts/start.sh --daemon --local-watcher

# Deploy daemon package (database update)
# ... set daemon_auto_restart=true ...

# Monitor daemon startup and health
./scripts/logs.sh worker_container | grep "daemon.monitor\|daemon_started"

# Monitor local watcher package processing
./scripts/logs.sh local_watcher | grep -i "package\|processing"

# Check if daemon recovered from crash
./scripts/logs.sh | grep "restart_succeeded"

# Stop everything
./scripts/stop.sh --remove
```

### Troubleshooting Service Failure
```bash
# Quick status check
./scripts/status.sh

# Full diagnostics
./scripts/status.sh --all

# View service logs
./scripts/logs.sh [service_name] -n 200

# Force restart failed service
./scripts/restart.sh [service_name] --hard

# Check all logs for errors
./scripts/logs.sh | grep -i "error\|fail\|exception"
```

### Rebuild After Code Changes
```bash
# Option 1: Rebuild and restart specific service
./scripts/restart.sh api --rebuild

# Option 2: Full rebuild and restart
./scripts/stop.sh --remove
./scripts/start.sh --build

# Option 3: Manual rebuild
docker-compose build --no-cache
./scripts/start.sh --daemon
```

### Production-like Testing
```bash
# Start with fresh environment
./scripts/stop.sh --remove
./scripts/start.sh --build --daemon

# Monitor daemon packages
./scripts/logs.sh worker_container | grep daemon

# Simulate failure by stopping daemon container
docker ps | grep daemon
docker stop <container_id>

# Watch auto-restart
./scripts/logs.sh | grep restart_succeeded

# Cleanup
./scripts/stop.sh --remove
```

---

## Environment Variables

Scripts read from `.env` file:

```bash
# Docker Compose
POSTGRES_USER=admin
POSTGRES_PASSWORD=secret123
POSTGRES_DB=crucibleaiagents

# Package Directory
PACKAGE_WATCHER_BASE_DIR=/Users/arifshaikh/Development/crucibleaiagents/package

# Daemon Monitoring
DAEMON_HEALTH_CHECK_INTERVAL=30
```

---

## Requirements

- **Docker**: 20.10+
- **Docker Compose**: 2.0+
- **bash**: 4.0+
- **Basic tools**: curl (for health checks), grep, awk, sed

Check requirements:
```bash
docker --version
docker-compose --version
bash --version
curl --version
```

---

## Tips & Tricks

### Colorless Output
All scripts support `--no-color`:
```bash
./scripts/start.sh --no-color
./scripts/logs.sh --no-color
```

### Use in Scripts/Automation
```bash
#!/bin/bash
./scripts/start.sh --daemon
./scripts/status.sh --check-api  # Will exit 0 if API is up, 1 if down
if [ $? -eq 0 ]; then
    echo "API is running"
fi
```

### Parallel Operations
```bash
# Terminal 1: Start and keep logs
./scripts/start.sh

# Terminal 2: Meanwhile, checking status
./scripts/status.sh --all

# Terminal 3: Tail specific service
./scripts/logs.sh api
```

### Filter and Count Errors
```bash
# Count ERROR events
./scripts/logs.sh -n 1000 --no-follow | grep -c "ERROR"

# Find services with issues
./scripts/logs.sh | grep "unhealthy\|failed\|error" | cut -d: -f1 | sort -u
```

### Integration with Systemd
Create `/etc/systemd/system/crucible-platform.service`:
```ini
[Unit]
Description=Crucible AI Platform
After=docker.service

[Service]
Type=forking
WorkingDirectory=/Users/arifshaikh/Development/crucibleaiagents
ExecStart=/bin/bash scripts/start.sh --daemon
ExecStop=/bin/bash scripts/stop.sh
User=arifshaikh

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl start crucible-platform
sudo systemctl enable crucible-platform
sudo systemctl status crucible-platform
```

---

## Troubleshooting

### Scripts not executable
```bash
chmod +x ./scripts/*.sh
```

### Docker not found
```bash
# Install Docker Desktop or Docker Engine for your OS
# macOS: brew install docker docker-compose
# Ubuntu: apt-get install docker.io docker-compose
```

### Services not starting
```bash
# Check logs in detail
./scripts/logs.sh -n 500 --no-follow

# Check docker-compose is valid
docker-compose config | head -50

# Try rebuilding
./scripts/stop.sh --remove
./scripts/start.sh --build
```

### Port conflicts
Services use ports: 5432 (DB), 8080 (API), 3000 (Frontend)
```bash
# Check what's using port 8080
lsof -i :8080

# Kill and restart
./scripts/restart.sh api --hard
```

---

## Support

For issues, check:
1. Logs: `./scripts/logs.sh -n 500`
2. Status: `./scripts/status.sh --all`
3. Docker: `docker ps -a`, `docker network ls`
4. Documentation: `docs/DAEMON_SECURITY.md`

