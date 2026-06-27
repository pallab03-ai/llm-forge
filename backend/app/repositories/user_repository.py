"""User repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=User)

    async def get_by_email(self, email: str) -> User | None:
        normalized = email.strip().lower()
        result = await self._session.execute(
            select(User).where(User.email == normalized)
        )
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        normalized = username.strip().lower()
        result = await self._session.execute(
            select(User).where(User.username == normalized)
        )
        return result.scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        return (await self.get_by_email(email)) is not None

    async def username_exists(self, username: str) -> bool:
        return (await self.get_by_username(username)) is not None
