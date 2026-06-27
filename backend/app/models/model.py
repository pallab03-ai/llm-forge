"""Model Registry ORM models.

A ``Model`` is a user-owned container; a ``ModelVersion`` is one
trained LoRA adapter (with an evaluation snapshot). Models have no
soft delete — use the version's ARCHIVED status instead. Only one
version per model may be PRODUCTION at a time.
"""

from __future__ import annotations

import enum
from uuid import UUID

from sqlalchemy import (
    JSON,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class ModelVersionStatus(str, enum.Enum):
    DRAFT = "draft"
    STAGING = "staging"
    PRODUCTION = "production"
    ARCHIVED = "archived"


class Model(BaseModel):
    """Table: `models`."""

    __tablename__ = "models"

    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="User who owns this model.",
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        doc="Human-readable model name.",
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Optional description of the model.",
    )

    versions: Mapped[list["ModelVersion"]] = relationship(
        "ModelVersion",
        back_populates="model",
        order_by="ModelVersion.version_number.desc()",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Model id={self.id} name={self.name!r} "
            f"owner={self.owner_id}>"
        )


class ModelVersion(BaseModel):
    """Table: `model_versions`."""

    __tablename__ = "model_versions"

    model_id: Mapped[UUID] = mapped_column(
        ForeignKey("models.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Parent model.",
    )

    training_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("training_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Training job that produced this adapter.",
    )

    evaluation_id: Mapped[UUID] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Evaluation used to validate this adapter.",
    )

    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Monotonically increasing version number (1, 2, 3, ...).",
    )

    artifact_path: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        doc="Path to the trained LoRA adapter artifact.",
    )

    metrics_snapshot: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        doc="Snapshot of evaluation metrics at version creation time.",
    )

    status: Mapped[ModelVersionStatus] = mapped_column(
        SAEnum(
            ModelVersionStatus,
            name="model_version_status",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=ModelVersionStatus.STAGING,
        server_default=ModelVersionStatus.STAGING.value,
        index=True,
        doc="Current lifecycle status.",
    )

    model: Mapped["Model"] = relationship(
        "Model",
        back_populates="versions",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ModelVersion id={self.id} model={self.model_id} "
            f"v{self.version_number} status={self.status!r}>"
        )
