"""UUID primary key mixin.

UUIDs are generated client-side via ``uuid4`` — no DB extension required.
"""

from uuid import UUID, uuid4

from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column


class UUIDMixin:
    id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid4,
        nullable=False,
        index=True,
    )
