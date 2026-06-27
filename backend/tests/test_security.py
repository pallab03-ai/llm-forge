"""Security hardening tests.

Covers the two invariants introduced in the Security Hardening Phase:

1. Case-insensitive uniqueness of ``users.email`` and ``users.username``.
   The application layer normalizes both fields to lowercase before
   persistence and lookup. The PostgreSQL database additionally enforces
   uniqueness via expression indexes on ``LOWER(email)`` and
   ``LOWER(username)`` (see migration ``0002_unique_lower_email_username``).

   SQLite (used in unit tests) does not support expression indexes, so the
   database-level enforcement is verified by a separate integration test
   pattern documented in the handoff report. The unit tests below verify
   the application-layer invariant: registering ``Alice@Example.com`` and
   then ``alice@example.com`` MUST be rejected with ``409 user_already_exists``.

2. Production JWT secret validation. ``Settings`` MUST refuse to instantiate
   when ``APP_ENV`` is ``production`` or ``staging`` and ``JWT_SECRET_KEY``
   still starts with the development-only prefix ``change-me-in-production``.
   This is enforced by a ``model_validator(mode="after")`` on ``Settings``.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.core.config import Settings


# ---------------------------------------------------------------------------
# Case-insensitive uniqueness (application layer)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_duplicate_email_different_casing(
    client: AsyncClient, user_payload: dict
):
    """Registering with a different email casing must be rejected.

    The first registration uses ``alice@example.com``. The second
    registration uses ``Alice@Example.com`` (different casing). The
    application normalizes both to lowercase, so the second registration
    collides with the first and must be rejected with ``409``.
    """
    first = await client.post("/api/v1/auth/register", json=user_payload)
    assert first.status_code == 201, first.text

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "Alice@Example.com",
            "username": "different_username",
            "password": "AnotherPass1!",
        },
    )

    assert response.status_code == 409
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "user_already_exists"


@pytest.mark.asyncio
async def test_register_duplicate_username_different_casing(
    client: AsyncClient, user_payload: dict
):
    """Registering with a different username casing must be rejected.

    The first registration uses ``alice``. The second registration uses
    ``Alice`` (different casing). The application normalizes both to
    lowercase, so the second registration collides with the first and
    must be rejected with ``409``.
    """
    first = await client.post("/api/v1/auth/register", json=user_payload)
    assert first.status_code == 201, first.text

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "different@example.com",
            "username": "Alice",
            "password": "AnotherPass1!",
        },
    )

    assert response.status_code == 409
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "user_already_exists"


@pytest.mark.asyncio
async def test_register_duplicate_email_and_username_different_casing(
    client: AsyncClient, user_payload: dict
):
    """Both fields colliding in different casing must be rejected."""
    first = await client.post("/api/v1/auth/register", json=user_payload)
    assert first.status_code == 201, first.text

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "ALICE@EXAMPLE.COM",
            "username": "ALICE",
            "password": "AnotherPass1!",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "user_already_exists"


# ---------------------------------------------------------------------------
# Production JWT secret validation
# ---------------------------------------------------------------------------


def test_production_startup_with_default_secret_rejected(monkeypatch: pytest.MonkeyPatch):
    """Settings must refuse to instantiate in production with the dev secret.

    We construct ``Settings`` directly with ``APP_ENV='production'`` and the
    default ``JWT_SECRET_KEY``. The ``model_validator`` must raise
    ``ValidationError`` (Pydantic's wrapper around ``ValueError``) so the
    process exits before any token is ever signed.
    """
    # Ensure no inherited env vars leak into the test.
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        Settings(APP_ENV="production")

    # The error message must mention the offending field so operators can
    # diagnose the failure quickly.
    errors = exc_info.value.errors()
    assert any(
        "_validate_production_secrets" in str(err.get("type", ""))
        or "JWT_SECRET_KEY" in str(err.get("msg", ""))
        for err in errors
    ), f"Expected JWT_SECRET_KEY validation error, got: {errors}"


def test_staging_startup_with_default_secret_rejected(monkeypatch: pytest.MonkeyPatch):
    """The same guard must apply to ``staging``.

    ``staging`` is treated as production-like because it is typically
    reachable from the public internet and shares secrets with production
    in some deployments.
    """
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings(APP_ENV="staging")


def test_production_startup_with_valid_secret_succeeds(monkeypatch: pytest.MonkeyPatch):
    """A real, non-default secret in production must be accepted."""
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    settings = Settings(
        APP_ENV="production",
        JWT_SECRET_KEY="a-real-strong-secret-generated-with-opens rand hex 32",
    )

    assert settings.APP_ENV == "production"
    assert settings.JWT_SECRET_KEY.startswith("a-real-strong-secret")


def test_development_startup_with_default_secret_succeeds(monkeypatch: pytest.MonkeyPatch):
    """The dev default must remain usable in development.

    This guards against accidentally over-tightening the validator and
    breaking local development / the test suite.
    """
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    # Should not raise.
    settings = Settings(APP_ENV="development")

    assert settings.APP_ENV == "development"


def test_production_env_case_insensitive(monkeypatch: pytest.MonkeyPatch):
    """``APP_ENV`` matching must be case-insensitive.

    Operators may legitimately set ``APP_ENV=Production`` or
    ``APP_ENV=PRODUCTION``. The validator must still catch the dev secret.
    """
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings(APP_ENV="PRODUCTION")

    with pytest.raises(ValidationError):
        Settings(APP_ENV="  Production  ")
