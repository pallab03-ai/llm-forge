"""Generic async repository base.

Provides common CRUD operations for any SQLAlchemy model that uses
`BaseModel` (UUID primary key). Subclasses add domain-specific queries.

Per engineering guardrails:
- Business logic MUST NOT live in API routes.
- All DB access goes through repositories.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)


class BaseRepository(Generic[ModelT]):
    """Generic async CRUD repository for `BaseModel` subclasses."""

    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self._session = session
        self._model = model

    @property
    def session(self) -> AsyncSession:
        return self._session

    @property
    def model(self) -> type[ModelT]:
        return self._model

    async def get_by_id(self, entity_id: UUID) -> ModelT | None:
        """Fetch a single entity by its UUID primary key."""
        result = await self._session.execute(
            select(self._model).where(self._model.id == entity_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self, *, limit: int = 100, offset: int = 0) -> list[ModelT]:
        """Return up to `limit` entities starting at `offset`."""
        result = await self._session.execute(
            select(self._model).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def add(self, entity: ModelT) -> ModelT:
        """Persist a new entity. Caller is responsible for committing."""
        self._session.add(entity)
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    async def delete(self, entity_id: UUID) -> bool:
        """Delete an entity by id. Returns True if a row was removed."""
        result = await self._session.execute(
            delete(self._model).where(self._model.id == entity_id)
        )
        return result.rowcount > 0

    async def commit(self) -> None:
        """Commit the current transaction."""
        await self._session.commit()

    async def rollback(self) -> None:
        """Roll back the current transaction."""
        await self._session.rollback()
