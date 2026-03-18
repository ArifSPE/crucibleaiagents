#!/usr/bin/env python3
"""
FastAPI daemon agent.

Runs a long-lived HTTP API inside the daemon container. The port is exposed to the
host by the platform when manifest.expose.port is configured.
"""

import os
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI

APP_NAME = os.getenv("APP_NAME", "FastAPI Daemon Agent")
DAEMON_PORT = int(os.getenv("DAEMON_PORT", "8000"))
STARTED_AT = datetime.now(timezone.utc)

app = FastAPI(title=APP_NAME)


@app.get("/")
def root() -> dict:
    """Public root endpoint for quick connectivity checks."""
    return {
        "service": APP_NAME,
        "status": "running",
        "started_at": STARTED_AT.isoformat(),
    }


@app.get("/health")
def health() -> dict:
    """Health endpoint used by daemon health checks."""
    now = datetime.now(timezone.utc)
    uptime_seconds = int((now - STARTED_AT).total_seconds())
    return {
        "status": "healthy",
        "service": APP_NAME,
        "timestamp": now.isoformat(),
        "uptime_seconds": uptime_seconds,
        "port": DAEMON_PORT,
    }


@app.get("/api/ping")
def ping() -> dict:
    """Simple API route intended for external callers."""
    return {
        "message": "pong",
        "service": APP_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=DAEMON_PORT)
