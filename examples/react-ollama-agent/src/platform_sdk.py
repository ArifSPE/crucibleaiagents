import time
import logging
from functools import wraps

# Optional: use telemetry if running in container environment
try:
    from sitecustomize import emit_event
except (ImportError, AttributeError):
    # Fallback for local development
    def emit_event(event_type: str, payload: dict):
        pass

# Export core tools for agent use
try:
    from tools import (
        LLMClient,
        LLMProvider,
        LLMResponse,
        ShellExecutor,
        ShellResult,
        HTTPClient,
        HTTPResponse,
        ToolRegistry,
        ToolParameter,
        ToolDefinition,
    )
    __all__ = [
        "get_logger",
        "step",
        "emit_event",
        "LLMClient",
        "LLMProvider",
        "LLMResponse",
        "ShellExecutor",
        "ShellResult",
        "HTTPClient",
        "HTTPResponse",
        "ToolRegistry",
        "ToolParameter",
        "ToolDefinition",
    ]
except ImportError:
    # Tools not available in this environment
    __all__ = ["get_logger", "step", "emit_event"]

def get_logger(name: str = "agent") -> logging.Logger:
    """
    Get a logger that automatically sends logs to the platform database.
    
    Args:
        name: Logger name (used for section detection). Common values:
              - "agent" (default): For agent execution logs
              - "system": For system/infrastructure logs  
              - "dependency": For dependency management logs
              - "network": For network/HTTP logs
    
    Returns:
        logging.Logger configured to send logs to platform
    
    Example:
        from platform_sdk import get_logger
        
        log = get_logger("agent")
        log.info("Starting agent execution")
        log.warning("Deprecated feature used")
        log.error("Failed to process query")
    """
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