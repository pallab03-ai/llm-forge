"""Deployment ORM model.

Exposes one ModelVersion as an inference endpoint.
Lifecycle: PENDING → DEPLOYING → ACTIVE, or → FAILED.
"""

from __future__ import annotations

import enum
from uuid import UUID

from sqlalchemy import Enum as SAEnum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class DeploymentStatus(str, enum.Enum):
    PENDING = "pending"
    DEPLOYING = "deploying"
    ACTIVE = "active"
    FAILED = "failed"


class Deployment(BaseModel):
    """Table: `deployments`."""

    __tablename__ = "deployments"

    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="User who owns this deployment.",
    )

    model_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("model_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="ModelVersion being deployed.",
    )

    deployment_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        doc="Human-readable deployment name.",
    )

    status: Mapped[DeploymentStatus] = mapped_column(
        SAEnum(
            DeploymentStatus,
            name="deployment_status",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=DeploymentStatus.PENDING,
        server_default=DeploymentStatus.PENDING.value,
        index=True,
        doc="Current lifecycle status.",
    )

    endpoint_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        doc="Public endpoint identifier/name.",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Deployment id={self.id} name={self.deployment_name!r} "
            f"status={self.status!r}>"
        )
