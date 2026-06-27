"""Dataset and DatasetVersion repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.dataset import Dataset, DatasetStatus, DatasetVersion
from app.repositories.base import BaseRepository


class DatasetRepository(BaseRepository[Dataset]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=Dataset)

    async def get_by_name(self, name: str) -> Dataset | None:
        normalized = name.strip().lower()
        result = await self._session.execute(
            select(Dataset).where(
                func.lower(Dataset.name) == normalized,
                Dataset.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def name_exists(self, name: str) -> bool:
        return (await self.get_by_name(name)) is not None

    async def list_active(
        self,
        *,
        owner_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Dataset]:
        stmt = select(Dataset).where(Dataset.deleted_at.is_(None))
        if owner_id is not None:
            stmt = stmt.where(Dataset.created_by == owner_id)
        stmt = stmt.order_by(Dataset.created_at.desc()).limit(limit).offset(offset)
        stmt = stmt.options(selectinload(Dataset.versions))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_active(self, *, owner_id: UUID | None = None) -> int:
        stmt = select(func.count(Dataset.id)).where(
            Dataset.deleted_at.is_(None)
        )
        if owner_id is not None:
            stmt = stmt.where(Dataset.created_by == owner_id)
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0

    async def get_by_id_and_owner(
        self, dataset_id: UUID, owner_id: UUID
    ) -> Dataset | None:
        # Returns None when the dataset does not exist OR is owned by a
        # different user; callers surface this as 403/404 without
        # leaking which case it was.
        result = await self._session.execute(
            select(Dataset)
            .where(
                Dataset.id == dataset_id,
                Dataset.created_by == owner_id,
                Dataset.deleted_at.is_(None),
            )
            .options(selectinload(Dataset.versions))
        )
        return result.scalar_one_or_none()

    async def soft_delete(
        self, dataset_id: UUID, *, owner_id: UUID | None = None
    ) -> bool:
        if owner_id is not None:
            dataset = await self.get_by_id_and_owner(dataset_id, owner_id)
        else:
            dataset = await self.get_by_id(dataset_id)
        if dataset is None or dataset.is_deleted:
            return False
        from datetime import datetime, timezone

        dataset.deleted_at = datetime.now(timezone.utc)
        dataset.status = DatasetStatus.DELETED
        await self._session.flush()
        return True


class DatasetVersionRepository(BaseRepository[DatasetVersion]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=DatasetVersion)

    async def get_latest_version_number(self, dataset_id: UUID) -> int:
        result = await self._session.execute(
            select(func.coalesce(func.max(DatasetVersion.version_number), 0))
            .where(DatasetVersion.dataset_id == dataset_id)
        )
        return result.scalar_one() or 0

    async def list_by_dataset(
        self, dataset_id: UUID
    ) -> list[DatasetVersion]:
        result = await self._session.execute(
            select(DatasetVersion)
            .where(DatasetVersion.dataset_id == dataset_id)
            .order_by(DatasetVersion.version_number.desc())
        )
        return list(result.scalars().all())

    async def get_by_dataset_and_version(
        self, dataset_id: UUID, version_number: int
    ) -> DatasetVersion | None:
        result = await self._session.execute(
            select(DatasetVersion).where(
                DatasetVersion.dataset_id == dataset_id,
                DatasetVersion.version_number == version_number,
            )
        )
        return result.scalar_one_or_none()