"""User ORM model. Passwords are stored only as bcrypt hashes."""

from __future__ import annotations

import enum

from sqlalchemy import Enum as SAEnum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class User(BaseModel):
    """Table: `users`."""

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

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} email={self.email!r} role={self.role!r}>"
