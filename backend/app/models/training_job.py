"""TrainingJob ORM model and domain types.

Represents a fine-tuning training job submitted by a user.
Each job references a dataset (and specific version) and tracks
its lifecycle through QUEUED → RUNNING → COMPLETED/FAILED/CANCELLED.

Per engineering guardrails:
- UUID primary keys.
- created_at / updated_at timestamps.
- Soft delete via deleted_at.
- No CREATED status — jobs start at QUEUED.
- TrainingConfig is a Pydantic v2 model with exactly 4 fields.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel as PydanticBaseModel
from pydantic import ConfigDict, Field, model_validator
from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TrainingJobStatus(str, enum.Enum):
    """Lifecycle status of a training job.

    No CREATED status — jobs are enqueued immediately upon creation.
    """

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TrainingType(str, enum.Enum):
    """Supported fine-tuning strategies."""

    SFT = "sft"
    LORA = "lora"
    QLORA = "qlora"
    PEFT = "peft"


# ---------------------------------------------------------------------------
# TrainingConfig (Pydantic v2 — stored as JSONB in the database)
# ---------------------------------------------------------------------------


class TrainingConfig(PydanticBaseModel):
    """Training hyperparameters — exactly 4 fields.

    Stored as JSONB in the training_jobs.configuration column.

    Limits are calibrated for a 16 GB T4 GPU (Colab free tier):
    - epochs: 1–10
    - batch_size: 1–64
    - learning_rate: 1e-7–1.0
    - max_seq_length: 64–8192

    Cross-field OOM guard: batch_size * max_seq_length must not exceed
    262144 (e.g. 64×4096 or 32×8192). This is a conservative heuristic
    to prevent out-of-memory errors on 16 GB VRAM.
    """

    model_config = ConfigDict(extra="forbid")

    epochs: int = Field(ge=1, le=10, description="Number of training epochs (1–10).")
    batch_size: int = Field(ge=1, le=64, description="Training batch size (1–64).")
    learning_rate: float = Field(ge=1e-7, le=1.0, description="Learning rate.")
    max_seq_length: int = Field(ge=64, le=8192, description="Maximum sequence length (64–8192).")

    @model_validator(mode="after")
    def _validate_oom_risk(self) -> "TrainingConfig":
        """Reject combinations likely to cause OOM on a 16 GB T4.

        Heuristic: batch_size × max_seq_length ≤ 262144.
        """
        if self.batch_size * self.max_seq_length > 262144:
            raise ValueError(
                f"batch_size × max_seq_length ({self.batch_size} × "
                f"{self.max_seq_length} = {self.batch_size * self.max_seq_length}) "
                f"exceeds the safe limit of 262144 for a 16 GB GPU. "
                f"Reduce batch_size or max_seq_length."
            )
        return self


# ---------------------------------------------------------------------------
# TrainingJob
# ---------------------------------------------------------------------------


class TrainingJob(BaseModel):
    """A fine-tuning training job.

    Table: `training_jobs`
    """

    __tablename__ = "training_jobs"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="User who submitted this training job.",
    )

    dataset_id: Mapped[UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Dataset to train on.",
    )

    dataset_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="CASCADE"),
        nullable=False,
        doc="Specific version of the dataset to use.",
    )

    status: Mapped[TrainingJobStatus] = mapped_column(
        SAEnum(
            TrainingJobStatus,
            name="training_job_status",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=TrainingJobStatus.QUEUED,
        server_default=TrainingJobStatus.QUEUED.value,
        index=True,
        doc="Current lifecycle status.",
    )

    base_model: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="HuggingFace model identifier (e.g. 'meta-llama/Llama-2-7b-hf').",
    )

    training_type: Mapped[TrainingType] = mapped_column(
        SAEnum(
            TrainingType,
            name="training_type",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        doc="Fine-tuning strategy (sft, lora, qlora, peft).",
    )

    configuration: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        doc="Training hyperparameters (epochs, batch_size, learning_rate, max_seq_length).",
    )

    artifact_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        doc="Path to the trained model artifact (set on completion).",
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp when the job started running.",
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp when the job finished (completed, failed, or cancelled).",
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Error details if the job failed.",
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        doc="Soft-delete timestamp. NULL means active.",
    )

    # Relationships
    dataset: Mapped["Dataset"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Dataset",
        lazy="selectin",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<TrainingJob id={self.id} status={self.status!r} "
            f"base_model={self.base_model!r} type={self.training_type!r}>"
        )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
