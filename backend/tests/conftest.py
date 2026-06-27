"""Pytest configuration and shared fixtures.

Phase 1 introduces a SQLite-backed test database so the full auth flow
can be exercised without requiring a running PostgreSQL instance.

The fixtures:
- build an in-memory SQLite engine,
- create all tables from the SQLAlchemy metadata,
- override the FastAPI `get_db` dependency to use that engine,
- provide an async `client` that talks to the app via the overridden DB.

Phase 2.1: switched the `client` fixture from the synchronous
``starlette.testclient.TestClient`` to ``httpx.AsyncClient`` with
``ASGITransport`` so it can be used inside ``async def`` tests with
``await client.post(...)``. The previous sync client caused
``TypeError: object Response can't be used in 'await' expression``.

Phase 4.1: added ML package mocks (torch, transformers, peft, trl,
bitsandbytes, accelerate, datasets) to sys.modules so that training
module tests can run without GPU/ML packages installed. These mocks
MUST be installed before any app imports happen.

Phase 4.2: added torch.bfloat16 mock alongside torch.float16 for
QLoRA bfloat16 compute dtype tests.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# ML package mocks — MUST be installed before any app imports
# ---------------------------------------------------------------------------
# The training module uses lazy imports (heavy ML packages are imported
# inside factory methods, not at module level). However, some tests
# directly import from these packages (e.g. `import torch` to check
# torch.float16, or `from peft import TaskType`). We pre-populate
# sys.modules with MagicMock objects so those imports succeed in test
# environments that don't have torch/transformers/peft/trl installed.

import sys
from unittest.mock import MagicMock


def _install_ml_mocks() -> None:
    """Pre-populate sys.modules with mock ML packages.

    This allows `import torch`, `from transformers import ...`, etc. to
    succeed even when the real packages aren't installed. Each mock module
    returns MagicMock instances for any attribute access, so code like
    `torch.float16`, `torch.__version__`, `torch.cuda.OutOfMemoryError`
    all work without the real package.
    """
    _ml_packages = [
        "torch",
        "torch.cuda",
        "torch.nn",
        "torch.utils",
        "torch.utils.data",
        "transformers",
        "transformers.models",
        "peft",
        "trl",
        "bitsandbytes",
        "accelerate",
        "datasets",
        "safetensors",
    ]

    for pkg in _ml_packages:
        if pkg not in sys.modules:
            sys.modules[pkg] = MagicMock()

    # Set commonly-accessed attributes to realistic values
    torch_mock = sys.modules["torch"]
    torch_mock.__version__ = "2.4.0"
    torch_mock.float16 = "float16"  # sentinel for test assertions
    torch_mock.bfloat16 = "bfloat16"  # sentinel for test assertions
    torch_mock.cuda.OutOfMemoryError = RuntimeError

    transformers_mock = sys.modules["transformers"]
    transformers_mock.__version__ = "4.50.0"

    peft_mock = sys.modules["peft"]
    peft_mock.__version__ = "0.13.0"

    trl_mock = sys.modules["trl"]
    trl_mock.__version__ = "0.12.0"

    bnb_mock = sys.modules["bitsandbytes"]
    bnb_mock.__version__ = "0.44.0"

    datasets_mock = sys.modules["datasets"]
    datasets_mock.__version__ = "3.0.0"


_install_ml_mocks()

# ---------------------------------------------------------------------------
# Standard imports (after ML mocks are installed)
# ---------------------------------------------------------------------------

import asyncio
from typing import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.user import User  # noqa: F401  (ensure model is registered)


# ---------------------------------------------------------------------------
# Event loop
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def event_loop():
    """Provide a session-scoped event loop for async fixtures."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Test database
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def test_engine():
    """Create a single in-memory SQLite engine shared across the session."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    return engine


@pytest.fixture(scope="session", autouse=True)
async def _create_tables(test_engine):
    """Create all tables once per test session."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield a clean async session for a single test.

    Tables are truncated between tests to keep state isolated.
    """
    session_factory = async_sessionmaker(
        bind=test_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async with session_factory() as session:
        # Truncate all tables for isolation.
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())
        await session.commit()
        yield session


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Return an async HTTPX client with the DB dependency overridden.

    Phase 2.1: switched from ``TestClient`` (sync) to ``AsyncClient`` so
    tests can ``await client.post(...)``. The DB override is installed
    before the client is created and removed after the test.
    """

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def app_instance():
    """Return the FastAPI app instance."""
    return app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def user_payload() -> dict:
    """Default registration payload."""
    return {
        "email": "alice@example.com",
        "username": "alice",
        "password": "S3cret!Pass",
    }


@pytest.fixture
def auth_headers_factory(client: AsyncClient):
    """Return a callable that registers a user and returns auth headers."""

    async def _make(payload: dict | None = None) -> dict:
        data = payload or {
            "email": "bob@example.com",
            "username": "bob",
            "password": "S3cret!Pass",
        }
        response = await client.post("/api/v1/auth/register", json=data)
        assert response.status_code == 201, response.text
        token = response.json()["data"]["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _make
