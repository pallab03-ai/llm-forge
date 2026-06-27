"""Dataset request / response schemas.

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

from app.models.dataset import DatasetFormat, DatasetStatus, DatasetType


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class DatasetCreateRequest(BaseModel):
    """Payload for `POST /api/v1/datasets` — create a dataset and upload v1."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable dataset name.",
    )
    description: str | None = Field(
        default=None,
        max_length=5000,
        description="Optional description.",
    )
    dataset_type: DatasetType = Field(
        ...,
        description="Semantic type: instruction_tuning, chat, or qa.",
    )
    format: DatasetFormat = Field(
        ...,
        description="File format: csv, json, or jsonl.",
    )


class DatasetVersionUploadRequest(BaseModel):
    """Payload for `POST /api/v1/datasets/{id}/versions` — upload a new version."""

    model_config = ConfigDict(extra="forbid")

    # No extra fields — the file comes as multipart upload form data.


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class DatasetVersionResponse(BaseModel):
    """Public representation of a dataset version."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dataset_id: UUID
    version_number: int
    file_size_bytes: int
    record_count: int
    duplicate_count: int
    validation_errors: str | None = None
    statistics: str | None = None
    created_at: datetime
    updated_at: datetime


class DatasetResponse(BaseModel):
    """Public representation of a dataset (without versions)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None
    dataset_type: DatasetType
    format: DatasetFormat
    status: DatasetStatus
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class DatasetDetailResponse(DatasetResponse):
    """Dataset with its versions included."""

    versions: list[DatasetVersionResponse] = Field(default_factory=list)


class DatasetStatisticsResponse(BaseModel):
    """Statistics for a dataset (aggregated across all versions)."""

    dataset_id: UUID
    dataset_name: str
    total_versions: int
    latest_version: int | None = None
    total_records: int = 0
    total_duplicates: int = 0
    total_size_bytes: int = 0
    versions: list[DatasetVersionResponse] = Field(default_factory=list)


class DatasetListResponse(BaseModel):
    """Paginated list of datasets."""

    items: list[DatasetResponse]
    total: int
    limit: int
    offset: int