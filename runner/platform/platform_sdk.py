import logging
import time
from functools import wraps

try:
    from sitecustomize import emit_event
except Exception:
    def emit_event(event_type: str, payload: dict):
        return None


def get_logger(name: str = "agent") -> logging.Logger:
    return logging.getLogger(name)


def step(name: str):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            t0 = time.time()
            emit_event("step_start", {"name": name})
            try:
                out = fn(*args, **kwargs)
                emit_event("step_end", {"name": name, "ms": (time.time() - t0) * 1000})
                return out
            except Exception as e:
                emit_event("step_error", {"name": name, "error": str(e), "ms": (time.time() - t0) * 1000})
                raise

        return wrapper

    return deco
