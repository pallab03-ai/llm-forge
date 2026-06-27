"""Model Registry request / response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.model import ModelVersionStatus


class ModelCreateRequest(BaseModel):
    """Payload for `POST /api/v1/models`."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable model name.",
    )
    description: str | None = Field(
        default=None,
        max_length=10000,
        description="Optional model description.",
    )


class ModelVersionCreateRequest(BaseModel):
    """Payload for `POST /api/v1/models/{id}/versions`."""

    model_config = ConfigDict(extra="forbid")

    training_job_id: UUID = Field(
        ...,
        description="Training job that produced the adapter.",
    )
    evaluation_id: UUID = Field(
        ...,
        description="Evaluation that validated the adapter.",
    )


class ModelVersionResponse(BaseModel):
    """Public representation of a model version."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    model_id: UUID
    training_job_id: UUID
    evaluation_id: UUID
    version_number: int
    artifact_path: str
    metrics_snapshot: dict | None = None
    status: ModelVersionStatus
    created_at: datetime
    updated_at: datetime


class ModelResponse(BaseModel):
    """Public representation of a model, including versions."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    name: str
    description: str | None = None
    versions: list[ModelVersionResponse] = []
    created_at: datetime
    updated_at: datetime


class ModelListResponse(BaseModel):
    """Paginated list of models."""

    items: list[ModelResponse]
    total: int
    limit: int
    offset: int
