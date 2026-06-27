"""Deployment request / response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.deployment import DeploymentStatus


class DeploymentCreateRequest(BaseModel):
    """Payload for `POST /api/v1/deployments`."""

    model_config = ConfigDict(extra="forbid")

    model_version_id: UUID = Field(
        ...,
        description="ModelVersion to deploy.",
    )
    deployment_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable deployment name.",
    )
    endpoint_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Endpoint identifier.",
    )


class DeploymentResponse(BaseModel):
    """Public representation of a deployment."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    model_version_id: UUID
    deployment_name: str
    status: DeploymentStatus
    endpoint_name: str
    created_at: datetime
    updated_at: datetime


class DeploymentListResponse(BaseModel):
    """Paginated list of deployments."""

    items: list[DeploymentResponse]
    total: int
    limit: int
    offset: int


class GenerateRequest(BaseModel):
    """Payload for `POST /api/v1/deployments/{id}/generate`."""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="Input prompt for the model.",
    )


class GenerateResponse(BaseModel):
    """Response from a generation request."""

    response: str
