"""
Shared pytest fixtures for the API test suite.

All tests use an in-memory SQLite database so no live PostgreSQL instance is
required.  The database is freshly created and torn down for every test
function, guaranteeing full isolation.
"""
import os
import sys

# ── required env vars — must be set BEFORE any application module is imported ─
from cryptography.fernet import Fernet as _Fernet

_FERNET_KEY = _Fernet.generate_key().decode()
os.environ["SECRETS_ENCRYPTION_KEY"] = _FERNET_KEY
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("STORAGE_DIR", "/tmp/test_crucible_storage")
os.environ.setdefault("ARCHIVE_DIR", "/tmp/test_crucible_archive")

# ── sys.path: tests are inside api/tests/, application root is api/ ───────────
_API_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)

# ── application imports (safe after env vars are set) ─────────────────────────
import pytest
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

import main as main_module
import utils.dependency as dep_module
from utils.db import Base
from schemas.model import AgentPackage, LlmProvider, PackageSchedule, PackageSecret, Runs
from main import app

# ── single shared SQLite engine with StaticPool (in-memory, thread-safe) ──────
_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestingSession = sessionmaker(bind=_engine, autocommit=False, autoflush=False)


@contextmanager
def _test_db_session():
    """Replacement for dep_module.db_session that uses the SQLite test engine."""
    db = _TestingSession()
    try:
        yield db
    finally:
        db.close()


# ── core fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture()
def client(monkeypatch):
    """
    Yield a Starlette TestClient wired to the SQLite test database.

    - Redirects the app lifespan's create_all() to the SQLite engine.
    - Replaces dep_module.db_session so routers use the same in-memory DB.
    - Creates all tables before the test and drops them after.
    """
    monkeypatch.setattr(main_module, "engine", _engine)
    monkeypatch.setattr(dep_module, "db_session", _test_db_session)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture()
def db(client):
    """
    Yield a raw SQLAlchemy session against the test database.

    Use this fixture to seed rows directly rather than going through the API.
    Always commits before yielding so that the TestClient's own sessions can
    see the seeded data.
    """
    session = _TestingSession()
    yield session
    session.close()


# ── reusable seed helpers ─────────────────────────────────────────────────────

@pytest.fixture()
def sample_package(db):
    """A persisted AgentPackage row available for use in tests."""
    pkg = AgentPackage(name="test-agent", version="1.0.0", description="Test agent package")
    db.add(pkg)
    db.commit()
    db.refresh(pkg)
    return pkg


@pytest.fixture()
def sample_provider(db):
    """A persisted LlmProvider row (local_ollama, no credentials)."""
    provider = LlmProvider(provider="local_ollama", description="Local Ollama instance")
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return provider


@pytest.fixture()
def sample_run(db, sample_package):
    """A persisted Runs row linked to sample_package."""
    run = Runs(agent_package_id=sample_package.id, status="pending")
    db.add(run)
    db.commit()
    db.refresh(run)
    return run
