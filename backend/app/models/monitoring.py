"""Monitoring ORM models.

Ponytail: only two tables are persisted. Aggregate metrics (count, average
latency, min/max, success rate) are computed on demand from
``DeploymentRequestLog`` via SQL aggregates — there is no separate
``DeploymentMetric`` cache table. The append-only log is the source of
truth; the service recomputes aggregates on each query.

A ``DeploymentHealth`` row stores the latest health snapshot per
deployment so the per-deployment health endpoint can return a stable
``last_checked`` timestamp without re-deriving it on every call.

PII: ``DeploymentRequestLog`` stores only metadata (lengths, latency,
status). No prompt text, no generated text.
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class RequestStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILURE = "failure"


class DeploymentHealthState(str, enum.Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class DeploymentRequestLog(BaseModel):
    """Table: ``deployment_request_logs``.

    Append-only audit log. One row per ``/generate`` call. Stores
    metadata only — never the prompt or response text.
    """

    __tablename__ = "deployment_request_logs"

    deployment_id: Mapped[UUID] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Deployment that served the request.",
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        doc="Server time when the request completed.",
    )

    latency_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="End-to-end inference latency in milliseconds.",
    )

    status: Mapped[RequestStatus] = mapped_column(
        SAEnum(
            RequestStatus,
            name="request_status",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        index=True,
        doc="Outcome of the inference call.",
    )

    prompt_length: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Length of the request prompt in characters.",
    )

    response_length: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        doc="Length of the generated response in characters (null on failure).",
    )

    # Error metadata — populated only when status = FAILURE. Stored as
    # three columns so the errors endpoint can return them directly
    # without a join.
    error_type: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Machine-readable error class (e.g. INFERENCE_ERROR).",
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Human-readable error message.",
    )

    error_status_code: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        doc="HTTP status code that would have been returned.",
    )

    __table_args__ = (
        Index(
            "ix_deployment_request_logs_deployment_timestamp",
            "deployment_id",
            "timestamp",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<DeploymentRequestLog id={self.id} "
            f"deployment={self.deployment_id} status={self.status!r}>"
        )


class DeploymentHealth(BaseModel):
    """Table: ``deployment_healths``.

    Latest health snapshot per deployment. Updated on every health check
    or every request (whichever path lands first). There is at most one
    row per deployment enforced by a unique constraint on
    ``deployment_id``; the model's own ``id`` PK is preserved for
    consistency with the rest of the ORM (every domain entity gets a
    UUID id).
    """

    __tablename__ = "deployment_healths"

    deployment_id: Mapped[UUID] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        doc="Deployment this health snapshot belongs to (one per deployment).",
    )

    health: Mapped[DeploymentHealthState] = mapped_column(
        SAEnum(
            DeploymentHealthState,
            name="deployment_health_state",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        doc="Latest health verdict.",
    )

    message: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Short human-readable reason for the current state.",
    )

    last_checked: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        doc="Server time when the snapshot was last updated.",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<DeploymentHealth deployment={self.deployment_id} "
            f"health={self.health!r}>"
        )
