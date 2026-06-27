"""UUID primary key mixin.

Provides a UUID primary key column for ORM models.
Uses PostgreSQL's native UUID type via SQLAlchemy's `Uuid` (SQLAlchemy 2.0+).

Per engineering guardrails:
- All domain entities MUST use UUID primary keys.
- UUIDs are generated client-side via Python's uuid4 (no DB extension required).
"""

from uuid import UUID, uuid4

from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column


class UUIDMixin:
    """Mixin that adds a UUID primary key column named `id`.

    The column is non-nullable, uses Python uuid4 as default, and is indexed
    implicitly via the primary key constraint.
    """

    id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid4,
        nullable=False,
        index=True,
    )
