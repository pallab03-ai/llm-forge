"""SQLAlchemy declarative base and abstract BaseModel.

All domain models inherit ``BaseModel`` and get a UUID ``id`` plus
``created_at`` / ``updated_at`` timestamps. No binary data in the DB.
"""

from sqlalchemy.orm import DeclarativeBase

from app.db.mixins.timestamp_mixin import TimestampMixin
from app.db.mixins.uuid_mixin import UUIDMixin


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 declarative base. Used by Alembic autogenerate."""


class BaseModel(UUIDMixin, TimestampMixin, Base):
    """Abstract base for all domain entities."""

    __abstract__ = True

