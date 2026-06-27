"""User ORM model.

Represents an authenticated platform user. Passwords are NEVER stored in
plain text — only bcrypt hashes via `password_hash`.

Per engineering guardrails:
- UUID primary key.
- created_at / updated_at timestamps.
- Email and username are unique.
- Role field supports future RBAC (Phase 2+).
"""

from __future__ import annotations

import enum
from uuid import UUID

from sqlalchemy import Enum as SAEnum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class UserRole(str, enum.Enum):
    """Platform roles.

    Phase 1 only enforces the field's existence and uniqueness; RBAC
    enforcement (authorization checks) is added in later phases.
    """

    USER = "user"
    ADMIN = "admin"


class User(BaseModel):
    """A platform user.

    Table: `users`
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    username: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    role: Mapped[UserRole] = mapped_column(
        SAEnum(
            UserRole,
            name="user_role",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=UserRole.USER,
        server_default=UserRole.USER.value,
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<User id={self.id} email={self.email!r} role={self.role!r}>"

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN
