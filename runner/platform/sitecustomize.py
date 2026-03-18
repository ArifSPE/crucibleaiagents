import json
import logging
import os
import sys
import traceback
from datetime import datetime
from urllib import request

RUN_ID = os.environ.get("RUN_ID")
API_BASE = os.environ.get("API_BASE_URL")
API_AUTH_TOKEN = os.environ.get("AGENTFLOW_RUNNER_API_TOKEN", "").strip() or os.environ.get("AGENTFLOW_API_TOKEN", "").strip()


def _request_headers(extra_headers=None):
    headers = dict(extra_headers or {})
    if API_AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {API_AUTH_TOKEN}"
    return headers


def _post(path: str, data: dict):
    if not (RUN_ID and API_BASE):
        return
    try:
        body = json.dumps(data).encode("utf-8")
        req = request.Request(
            f"{API_BASE}{path}",
            data=body,
            headers=_request_headers({"Content-Type": "application/json"}),
            method="POST",
        )
        request.urlopen(req, timeout=2)
    except Exception:
        pass


def emit_event(event_type: str, payload: dict):
    evt = {
        "type": event_type,
        "run_id": RUN_ID,
        "ts": datetime.utcnow().isoformat() + "Z",
        "payload": payload,
    }
    _post(f"/runs/{RUN_ID}/events", evt)


class ApiLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            emit_event("log", {
                "level": record.levelname,
                "logger": record.name,
                "message": msg,
            })
        except Exception:
            pass


def _install_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    h = ApiLogHandler()
    h.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(h)


def _install_excepthook():
    def hook(exc_type, exc, tb):
        emit_event("exception", {
            "exc_type": getattr(exc_type, "__name__", str(exc_type)),
            "message": str(exc),
            "stack": "".join(traceback.format_tb(tb))[-4000:],
        })
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = hook


def _boot():
    emit_event("runner_boot", {"python": sys.version})
    _install_logging()
    _install_excepthook()


_boot()
