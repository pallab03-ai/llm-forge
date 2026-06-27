"""Generic async repository base.

Provides common CRUD operations for any SQLAlchemy model that uses
``BaseModel``. All DB access in the API layer goes through repositories.
"""

from __future__ import annotations

from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)


class BaseRepository(Generic[ModelT]):
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
        result = await self._session.execute(
            select(self._model).where(self._model.id == entity_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self, *, limit: int = 100, offset: int = 0) -> list[ModelT]:
        result = await self._session.execute(
            select(self._model).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def add(self, entity: ModelT) -> ModelT:
        self._session.add(entity)
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    async def delete(self, entity_id: UUID) -> bool:
        result = await self._session.execute(
            delete(self._model).where(self._model.id == entity_id)
        )
        return result.rowcount > 0

    async def commit(self) -> None:
        await self._session.commit()
