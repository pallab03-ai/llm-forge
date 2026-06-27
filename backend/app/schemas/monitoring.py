"""Monitoring request / response schemas.

Pydantic response models for the monitoring API. All schemas use
``from_attributes=True`` so they can be built directly from ORM rows.
The response shapes are flat — no nested history arrays or paginated
request lists, which keeps the dashboard rendering trivial.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.monitoring import DeploymentHealthState, RequestStatus


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


class DashboardResponse(BaseModel):
    """Aggregate metrics for the current user's deployments."""

    model_config = ConfigDict(from_attributes=True)

    deployment_count: int = Field(
        ..., ge=0, description="Total deployments owned by the user."
    )
    active_deployments: int = Field(
        ..., ge=0, description="Deployments currently in ACTIVE status."
    )
    failed_deployments: int = Field(
        ..., ge=0, description="Deployments currently in FAILED status."
    )
    total_requests: int = Field(
        ...,
        ge=0,
        description="Lifetime request count across the user's deployments.",
    )
    success_rate: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Share of successful requests (0.0 if no requests).",
    )
    average_latency_ms: float = Field(
        ...,
        ge=0.0,
        description="Mean latency across the user's requests (0 if no requests).",
    )


# ---------------------------------------------------------------------------
# Per-deployment health
# ---------------------------------------------------------------------------


class DeploymentHealthResponse(BaseModel):
    """Health snapshot for a single deployment."""

    model_config = ConfigDict(from_attributes=True)

    deployment_id: UUID
    status: str = Field(
        ...,
        description="Deployment lifecycle status (pending/deploying/active/failed).",
    )
    health: DeploymentHealthState
    last_checked: datetime
    message: str = Field(..., description="Short reason for the current health state.")


# ---------------------------------------------------------------------------
# Per-deployment metrics
# ---------------------------------------------------------------------------


class DeploymentMetricsResponse(BaseModel):
    """Aggregate metrics for a single deployment."""

    model_config = ConfigDict(from_attributes=True)

    request_count: int = Field(..., ge=0)
    success_count: int = Field(..., ge=0)
    failure_count: int = Field(..., ge=0)
    average_latency_ms: float = Field(..., ge=0.0)
    min_latency_ms: float = Field(..., ge=0.0)
    max_latency_ms: float = Field(..., ge=0.0)


# ---------------------------------------------------------------------------
# Per-deployment request log
# ---------------------------------------------------------------------------


class RequestLogItem(BaseModel):
    """One row of the deployment's request log."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    timestamp: datetime
    latency_ms: int
    status: RequestStatus
    prompt_length: int
    response_length: int | None = None


class RequestLogListResponse(BaseModel):
    """Paginated request log for a single deployment."""

    items: list[RequestLogItem]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Per-deployment error log
# ---------------------------------------------------------------------------


class ErrorLogItem(BaseModel):
    """One failed request, surfaced as an error event."""

    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    error_type: str
    message: str
    status_code: int


class ErrorLogListResponse(BaseModel):
    """Paginated error log for a single deployment."""

    items: list[ErrorLogItem]
    total: int
    limit: int
    offset: int
