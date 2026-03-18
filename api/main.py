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
from routers import packages, schedules, secrets, runs, llm_providers

# Secure default: only allow localhost for development unless overridden
from utils.config import ( _CORS_ORIGINS_DEFAULT,STORAGE_DIR, 
    ARCHIVE_DIR, ALLOWED_LLM_PROVIDERS, LLM_PROVIDER_CREDENTIAL_TEMPLATES)

_LOGGER = get_logger("api.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    Base.metadata.create_all(bind=engine)
    _LOGGER.info("Database tables created successfully.")
    yield
    # shutdown (optional cleanup here)


app = FastAPI(title="Crucible AI Agents Platform API", 
              version="1.0",
              docs_url="/docs",
              redoc_url="/redoc",
              openapi_url="/openapi.json",
              lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv('CORS_ORIGINS', _CORS_ORIGINS_DEFAULT).split(","),
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Agentflow-Token", "X-Agentflow-Source"],
)

app.include_router(packages.router)
app.include_router(schedules.router)
app.include_router(secrets.router)
app.include_router(runs.router)
app.include_router(llm_providers.router)


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
   uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
