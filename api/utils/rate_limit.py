"""Shared rate-limiter instance for FastAPI routes.

Import `limiter` in routers to apply per-endpoint limits.
Wire it into the FastAPI app in main.py via:

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
