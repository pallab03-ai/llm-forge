"""Evaluation ORM model.

An evaluation runs a trained LoRA adapter against a dataset version and
stores ROUGE-L, BERTScore, and semantic-similarity metrics. Evaluations
are immutable — no soft delete.
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class EvaluationStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Evaluation(BaseModel):
    """Table: `evaluations`."""

    __tablename__ = "evaluations"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="User who requested this evaluation.",
    )

    dataset_id: Mapped[UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Dataset used for evaluation.",
    )

    dataset_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="CASCADE"),
        nullable=False,
        doc="Specific dataset version evaluated.",
    )

    model_id: Mapped[UUID] = mapped_column(
        ForeignKey("training_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Trained model (training_jobs.id) whose adapter is evaluated.",
    )

    status: Mapped[EvaluationStatus] = mapped_column(
        SAEnum(
            EvaluationStatus,
            name="evaluation_status",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=EvaluationStatus.PENDING,
        server_default=EvaluationStatus.PENDING.value,
        index=True,
        doc="Current lifecycle status.",
    )

    rouge_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        doc="ROUGE-L F1 score (0.0–1.0).",
    )

    bertscore_precision: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        doc="BERTScore precision (0.0–1.0).",
    )

    bertscore_recall: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        doc="BERTScore recall (0.0–1.0).",
    )

    bertscore_f1: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        doc="BERTScore F1 (0.0–1.0).",
    )

    semantic_similarity: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        doc="Mean semantic similarity (0.0–1.0).",
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp when evaluation started running.",
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp when evaluation finished (completed or failed).",
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Error details if the evaluation failed.",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Evaluation id={self.id} status={self.status!r} "
            f"model_id={self.model_id!r}>"
        )
