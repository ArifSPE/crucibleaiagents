"""Structured logging helpers shared across all Crucible platform components.

Every log line is a JSON object with a consistent schema:

    {
        "timestamp": "2026-03-17T14:50:00.123456+00:00",
        "level":     "INFO",
        "component": "worker.executor",
        "event_type":"agent.run.started",
        "message":   "Agent run started",
        "run_id":    "abc123",
        ...extra fields...
    }

Usage (any module — api, worker, watcher, scheduler, runner):

    from shared.logger import get_logger, log_event, log_exception
    import logging

    LOGGER = get_logger("worker.executor")

    log_event(LOGGER, logging.INFO,    "agent.run.started",  "Agent run started",  run_id="abc123")
    log_event(LOGGER, logging.WARNING, "agent.run.slow",     "Run is taking long", run_id="abc123")
    log_exception(LOGGER,              "agent.run.failed",   "Unhandled exception", run_id="abc123")

Environment variables:
    AGENTFLOW_LOG_LEVEL   — one of DEBUG / INFO / WARNING / ERROR  (default: INFO)
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

_CONFIGURED = False


def _normalize_level(level_name: str) -> int:
    return getattr(logging, (level_name or "INFO").upper(), logging.INFO)


def configure_logging() -> None:
    """Configure process-wide logging once (idempotent)."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = _normalize_level(os.getenv("AGENTFLOW_LOG_LEVEL", "INFO"))
    logging.basicConfig(level=level, format="%(message)s")
    _CONFIGURED = True


def get_logger(component: str) -> logging.Logger:
    """Return a logger named after *component* (e.g. ``"worker.executor"``).

    Calling ``configure_logging()`` first ensures the root handler is set up
    before any log records are created.
    """
    configure_logging()
    return logging.getLogger(component)


def _build_payload(
    level: str,
    component: str,
    event_type: str,
    message: str,
    **fields: Any,
) -> str:
    payload: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "component": component,
        "event_type": event_type,
        "message": message,
    }
    for key, value in fields.items():
        if value is not None:
            payload[key] = value
    return json.dumps(payload, default=str, ensure_ascii=True)


def log_event(
    logger: logging.Logger,
    level: int,
    event_type: str,
    message: str,
    **fields: Any,
) -> None:
    """Emit a structured log line at *level* (no traceback)."""
    payload = _build_payload(
        logging.getLevelName(level), logger.name, event_type, message, **fields
    )
    logger.log(level, payload)


def log_exception(
    logger: logging.Logger,
    event_type: str,
    message: str,
    **fields: Any,
) -> None:
    """Emit a structured ERROR line including the active exception traceback."""
    payload = _build_payload("ERROR", logger.name, event_type, message, **fields)
    logger.error(payload, exc_info=True)
