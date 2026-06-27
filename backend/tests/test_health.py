"""Health endpoint tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_success_envelope(client: AsyncClient) -> None:
    """Health endpoint should return the standard success envelope."""
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "healthy"
    assert "version" in body["data"]
    assert "environment" in body["data"]


@pytest.mark.asyncio
async def test_health_includes_version(client: AsyncClient) -> None:
    """Health endpoint should expose the application version."""
    response = await client.get("/api/v1/health")
    body = response.json()

    assert body["data"]["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_root_path_serves_docs(client: AsyncClient) -> None:
    """OpenAPI docs should be available at /docs."""
    response = await client.get("/docs")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_openapi_schema_available(client: AsyncClient) -> None:
    """OpenAPI schema should be generated and accessible."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "openapi" in schema
    assert "paths" in schema
    assert "/api/v1/health" in schema["paths"]
