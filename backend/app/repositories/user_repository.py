"""User repository.

Encapsulates all database access for the `User` entity.
The service layer MUST go through this repository rather than touching
the session directly.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Async repository for `User`."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=User)

    async def get_by_email(self, email: str) -> User | None:
        """Fetch a user by their unique email address (case-insensitive)."""
        normalized = email.strip().lower()
        result = await self._session.execute(
            select(User).where(User.email == normalized)
        )
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        """Fetch a user by their unique username (case-insensitive)."""
        normalized = username.strip().lower()
        result = await self._session.execute(
            select(User).where(User.username == normalized)
        )
        return result.scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        """Return True if a user with this email already exists."""
        return (await self.get_by_email(email)) is not None

    async def username_exists(self, username: str) -> bool:
        """Return True if a user with this username already exists."""
        return (await self.get_by_username(username)) is not None
