"""Evaluation request / response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.evaluation import EvaluationStatus


class EvaluationCreateRequest(BaseModel):
    """Payload for `POST /api/v1/evaluations`."""

    model_config = ConfigDict(extra="forbid")

    model_id: UUID = Field(
        ...,
        description="UUID of the trained model (training_jobs.id) to evaluate.",
    )
    dataset_id: UUID = Field(
        ...,
        description="UUID of the dataset to evaluate against.",
    )
    dataset_version_id: UUID = Field(
        ...,
        description="UUID of the specific dataset version to use.",
    )


class EvaluationResponse(BaseModel):
    """Public representation of an evaluation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    dataset_id: UUID
    dataset_version_id: UUID
    model_id: UUID
    status: EvaluationStatus
    rouge_score: float | None = None
    bertscore_precision: float | None = None
    bertscore_recall: float | None = None
    bertscore_f1: float | None = None
    semantic_similarity: float | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class EvaluationListResponse(BaseModel):
    """Paginated list of evaluations."""

    items: list[EvaluationResponse]
    total: int
    limit: int
    offset: int
