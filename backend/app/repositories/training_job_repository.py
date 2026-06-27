"""TrainingJob repository."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.training_job import TrainingJob, TrainingJobStatus
from app.repositories.base import BaseRepository


class TrainingJobRepository(BaseRepository[TrainingJob]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=TrainingJob)

    async def create(self, job: TrainingJob) -> TrainingJob:
        return await self.add(job)

    async def get_by_id(self, job_id: UUID) -> TrainingJob | None:
        result = await self._session.execute(
            select(TrainingJob).where(
                TrainingJob.id == job_id,
                TrainingJob.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TrainingJob]:
        stmt = (
            select(TrainingJob)
            .where(
                TrainingJob.user_id == user_id,
                TrainingJob.deleted_at.is_(None),
            )
            .order_by(TrainingJob.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_user(self, user_id: UUID) -> int:
        stmt = select(func.count(TrainingJob.id)).where(
            TrainingJob.user_id == user_id,
            TrainingJob.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0

    async def count_active_jobs(self, user_id: UUID) -> int:
        # Enforces the "1 active job per user" constraint.
        stmt = select(func.count(TrainingJob.id)).where(
            TrainingJob.user_id == user_id,
            TrainingJob.deleted_at.is_(None),
            TrainingJob.status.in_(
                [TrainingJobStatus.QUEUED, TrainingJobStatus.RUNNING]
            ),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0

    async def update_status(
        self,
        job_id: UUID,
        status: TrainingJobStatus,
        *,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> TrainingJob | None:
        job = await self.get_by_id(job_id)
        if job is None:
            return None
        job.status = status
        if started_at is not None:
            job.started_at = started_at
        if completed_at is not None:
            job.completed_at = completed_at
        await self._session.flush()
        await self._session.refresh(job)
        return job
