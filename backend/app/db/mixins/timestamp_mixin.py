"""Timestamp mixin.

Provides `created_at` and `updated_at` columns for ORM models.
`updated_at` is automatically refreshed on UPDATE via SQLAlchemy's
`onupdate` hook.

Per engineering guardrails:
- Database MUST use timestamps for auditability.
"""

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """Mixin that adds `created_at` and `updated_at` timestamp columns.

    - `created_at`: set on INSERT, never updated.
    - `updated_at`: set on INSERT, refreshed on every UPDATE.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
