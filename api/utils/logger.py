"""API logger compatibility layer.

Canonical implementation lives in shared logger package so API, watcher,
worker, and scheduler can all use the same structured logging contract.
"""

from importlib import import_module
from pathlib import Path
import sys
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class _LocalLoggerModule:
    _configured = False

    @staticmethod
    def _normalize_level(level_name: str) -> int:
        return getattr(logging, (level_name or "INFO").upper(), logging.INFO)

    @classmethod
    def configure_logging(cls) -> None:
        if cls._configured:
            return
        level = cls._normalize_level(os.getenv("AGENTFLOW_LOG_LEVEL", "INFO"))
        logging.basicConfig(level=level, format="%(message)s")
        cls._configured = True

    @classmethod
    def get_logger(cls, component: str) -> logging.Logger:
        cls.configure_logging()
        return logging.getLogger(component)

    @staticmethod
    def _build_payload(level: str, component: str, event_type: str, message: str, **fields: Any) -> str:
        payload = {
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

    @classmethod
    def log_event(cls, logger: logging.Logger, level: int, event_type: str, message: str, **fields: Any) -> None:
        payload = cls._build_payload(logging.getLevelName(level), logger.name, event_type, message, **fields)
        logger.log(level, payload)

    @classmethod
    def log_exception(cls, logger: logging.Logger, event_type: str, message: str, **fields: Any) -> None:
        payload = cls._build_payload("ERROR", logger.name, event_type, message, **fields)
        logger.error(payload, exc_info=True)


def _load_logger_module():
    for module_name in ("shared.logger", "shared.shared.logger"):
        try:
            return import_module(module_name)
        except ModuleNotFoundError:
            continue
    return _LocalLoggerModule


_LOGGER_MODULE = _load_logger_module()

configure_logging = _LOGGER_MODULE.configure_logging
get_logger = _LOGGER_MODULE.get_logger
log_event = _LOGGER_MODULE.log_event
log_exception = _LOGGER_MODULE.log_exception

__all__ = ["configure_logging", "get_logger", "log_event", "log_exception"]

