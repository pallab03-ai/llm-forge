"""Dataset and DatasetVersion ORM models.

Each dataset can have multiple versioned snapshots. ``deleted_at`` is
the soft-delete marker; NULL means active. ``DatasetVersion.created_at``
serves as the upload timestamp.
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class DatasetFormat(str, enum.Enum):
    CSV = "csv"
    JSON = "json"
    JSONL = "jsonl"


class DatasetType(str, enum.Enum):
    INSTRUCTION_TUNING = "instruction_tuning"
    CHAT = "chat"
    QA = "qa"


class DatasetStatus(str, enum.Enum):
    UPLOADING = "uploading"
    VALIDATING = "validating"
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"


class Dataset(BaseModel):
    """Table: `datasets`."""

    __tablename__ = "datasets"

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        doc="Human-readable dataset name.",
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Optional description of the dataset.",
    )

    dataset_type: Mapped[DatasetType] = mapped_column(
        SAEnum(
            DatasetType,
            name="dataset_type",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        doc="Semantic type (instruction_tuning, chat, qa).",
    )

    format: Mapped[DatasetFormat] = mapped_column(
        SAEnum(
            DatasetFormat,
            name="dataset_format",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        doc="File format (csv, json, jsonl).",
    )

    status: Mapped[DatasetStatus] = mapped_column(
        SAEnum(
            DatasetStatus,
            name="dataset_status",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=DatasetStatus.UPLOADING,
        server_default=DatasetStatus.UPLOADING.value,
        doc="Current lifecycle status.",
    )

    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="User who created this dataset.",
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        doc="Soft-delete timestamp. NULL means active.",
    )

    versions: Mapped[list["DatasetVersion"]] = relationship(
        "DatasetVersion",
        back_populates="dataset",
        order_by="DatasetVersion.version_number.desc()",
        lazy="selectin",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Dataset id={self.id} name={self.name!r} "
            f"type={self.dataset_type!r} status={self.status!r}>"
        )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class DatasetVersion(BaseModel):
    """Table: `dataset_versions`."""

    __tablename__ = "dataset_versions"

    dataset_id: Mapped[UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Parent dataset.",
    )

    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Monotonically increasing version number (1, 2, 3, ...).",
    )

    file_path: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        doc="Relative path to the stored file on local filesystem.",
    )

    file_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Size of the uploaded file in bytes.",
    )

    record_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Number of records in this version.",
    )

    duplicate_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Number of duplicate records detected within this file.",
    )

    validation_errors: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="JSON-encoded list of validation errors, if any.",
    )

    statistics: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="JSON-encoded statistics blob (avg lengths, etc.).",
    )

    dataset: Mapped["Dataset"] = relationship(
        "Dataset",
        back_populates="versions",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<DatasetVersion id={self.id} dataset={self.dataset_id} "
            f"v{self.version_number} records={self.record_count}>"
        )