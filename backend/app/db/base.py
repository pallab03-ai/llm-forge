"""SQLAlchemy declarative base and shared BaseModel.

This module exposes:
- `Base`: the SQLAlchemy `DeclarativeBase` used by Alembic for autogenerate.
- `BaseModel`: a concrete base class that all domain models inherit from.
  It composes the UUID primary key mixin and the timestamp mixin so every
  domain entity has a UUID `id`, `created_at`, and `updated_at` by default.

Per engineering guardrails:
- All domain entities MUST use UUID primary keys.
- All domain entities MUST have created_at and updated_at timestamps.
- No binary files in the database.
"""

from sqlalchemy.orm import DeclarativeBase

from app.db.mixins.timestamp_mixin import TimestampMixin
from app.db.mixins.uuid_mixin import UUIDMixin


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 declarative base.

    Used by Alembic's autogenerate to discover tables.
    """


class BaseModel(UUIDMixin, TimestampMixin, Base):
    """Abstract base model for all domain entities.

    Inherits:
        - UUIDMixin: provides `id: UUID` primary key.
        - TimestampMixin: provides `created_at`, `updated_at`.

    Concrete models should subclass this and add their own columns.
    Marked abstract so SQLAlchemy does not create a table for it.
    """

    __abstract__ = True

