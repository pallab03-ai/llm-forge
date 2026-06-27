"""Training job request / response schemas.

All schemas are Pydantic v2 models. They are the only types allowed to
cross the API boundary.

Per engineering guardrails:
- Typed request/response models are mandatory.
- Response envelope is `{success, data}` or `{success, error}`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.training_job import TrainingConfig, TrainingJobStatus, TrainingType


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class TrainingJobCreateRequest(BaseModel):
    """Payload for `POST /api/v1/training-jobs` — create a training job."""

    model_config = ConfigDict(extra="forbid")

    dataset_id: UUID = Field(
        ...,
        description="UUID of the dataset to train on.",
    )
    dataset_version_id: UUID = Field(
        ...,
        description="UUID of the specific dataset version to train on.",
    )
    base_model: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Base model identifier (e.g. 'meta-llama/Llama-3.1-8B').",
    )
    training_type: TrainingType = Field(
        ...,
        description="Training type: sft, lora, qlora, or peft.",
    )
    configuration: TrainingConfig = Field(
        ...,
        description="Training hyperparameters (epochs, batch_size, learning_rate, max_seq_length).",
    )


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class TrainingJobResponse(BaseModel):
    """Public representation of a training job."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    dataset_id: UUID
    dataset_version_id: UUID
    status: TrainingJobStatus
    base_model: str
    training_type: TrainingType
    configuration: dict[str, Any]
    artifact_path: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class TrainingJobListResponse(BaseModel):
    """Paginated list of training jobs."""

    items: list[TrainingJobResponse]
    total: int
    limit: int
    offset: int
