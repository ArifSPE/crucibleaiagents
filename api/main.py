import logging
import os
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone
from utils.db import Base, engine
import schemas.model as model  # noqa: F401  # Import models so SQLAlchemy registers table metadata
from utils.logger import get_logger,log_event, log_exception
from contextlib import asynccontextmanager
import uvicorn
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from utils.rate_limit import limiter
from routers import packages, schedules, secrets, runs, llm_providers, chat, mcp, mcp_registry

# Secure default: only allow localhost for development unless overridden
from utils.config import ( _CORS_ORIGINS_DEFAULT,STORAGE_DIR, 
    ARCHIVE_DIR, ALLOWED_LLM_PROVIDERS, LLM_PROVIDER_CREDENTIAL_TEMPLATES)

_LOGGER = get_logger("api.main")
_environment = os.getenv("ENVIRONMENT", "production").strip().lower()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    Base.metadata.create_all(bind=engine)
    _LOGGER.info("Database tables created successfully.")
    yield
    # shutdown (optional cleanup here)


app = FastAPI(title="Crucible AI Agents Platform API", 
              version="1.0",
              docs_url="/docs" if _environment == "development" else None,
              redoc_url="/redoc" if _environment == "development" else None,
              openapi_url="/openapi.json" if _environment == "development" else None,
              lifespan=lifespan
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_cors_origins = os.getenv('CORS_ORIGINS', _CORS_ORIGINS_DEFAULT).split(",")
if "*" in _cors_origins and _environment != "development":
    raise RuntimeError(
        "CORS wildcard '*' is not permitted in non-development environments. "
        "Set CORS_ORIGINS to a comma-separated list of explicit origins."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Agentflow-Token", "X-Agentflow-Source"],
)

app.include_router(packages.router)
app.include_router(schedules.router)
app.include_router(secrets.router)
app.include_router(runs.router)
app.include_router(llm_providers.router)
app.include_router(chat.router)
app.include_router(mcp.router)
app.include_router(mcp_registry.router)


@app.get("/health")
def health() -> dict:
    """Lightweight health endpoint for platform readiness checks."""
    return {
        "status": "ok",
        "service": "api",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


#TODO Implement later
#app.middleware("http")(require_api_authentication)


if __name__ == "__main__":
    environment = os.getenv("ENVIRONMENT", "production").strip().lower()
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=(environment == "development"),
    )
