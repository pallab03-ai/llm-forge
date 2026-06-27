"""Authentication endpoint tests.

Covers:
- successful registration
- duplicate email / username rejection
- successful login
- invalid credentials rejection
- authenticated `/me` endpoint
- token validation edge cases
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient, user_payload: dict):
    response = await client.post("/api/v1/auth/register", json=user_payload)

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 24 * 60 * 60
    assert isinstance(data["access_token"], str) and len(data["access_token"]) > 20

    user = data["user"]
    assert user["email"] == user_payload["email"]
    assert user["username"] == user_payload["username"]
    assert user["role"] == "user"
    assert "password" not in user
    assert "password_hash" not in user


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, user_payload: dict):
    await client.post("/api/v1/auth/register", json=user_payload)

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": user_payload["email"],
            "username": "different_username",
            "password": "AnotherPass1!",
        },
    )

    assert response.status_code == 409
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "user_already_exists"


@pytest.mark.asyncio
async def test_register_duplicate_username(client: AsyncClient, user_payload: dict):
    await client.post("/api/v1/auth/register", json=user_payload)

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "different@example.com",
            "username": user_payload["username"],
            "password": "AnotherPass1!",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "user_already_exists"


@pytest.mark.asyncio
async def test_register_password_too_short(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "short@example.com",
            "username": "shorty",
            "password": "abc",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_invalid_email(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "not-an-email",
            "username": "validuser",
            "password": "ValidPass1!",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_normalizes_email_and_username(
    client: AsyncClient, user_payload: dict
):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": user_payload["email"].upper(),
            "username": user_payload["username"].upper(),
            "password": user_payload["password"],
        },
    )
    assert response.status_code == 201
    user = response.json()["data"]["user"]
    assert user["email"] == user_payload["email"]
    assert user["username"] == user_payload["username"]


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, user_payload: dict):
    await client.post("/api/v1/auth/register", json=user_payload)

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": user_payload["email"], "password": user_payload["password"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["token_type"] == "bearer"
    assert body["data"]["user"]["email"] == user_payload["email"]


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient, user_payload: dict):
    await client.post("/api/v1/auth/register", json=user_payload)

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": user_payload["email"], "password": "WrongPassword1!"},
    )

    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_login_unknown_user(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "Anything1!"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


# ---------------------------------------------------------------------------
# /me
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_me_authenticated(client: AsyncClient, auth_headers_factory):
    headers = await auth_headers_factory()

    response = await client.get("/api/v1/auth/me", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["email"] == "bob@example.com"
    assert body["data"]["username"] == "bob"


@pytest.mark.asyncio
async def test_me_missing_token(client: AsyncClient):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "missing_token"


@pytest.mark.asyncio
async def test_me_invalid_token(client: AsyncClient):
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


@pytest.mark.asyncio
async def test_me_malformed_authorization_header(client: AsyncClient):
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "NotBearer something"},
    )
    assert response.status_code == 401
