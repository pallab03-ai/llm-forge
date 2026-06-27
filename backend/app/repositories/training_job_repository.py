"""TrainingJob repository.

Encapsulates all database access for the `TrainingJob` entity.
The service layer MUST go through this repository rather than
touching the session directly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.training_job import TrainingJob, TrainingJobStatus
from app.repositories.base import BaseRepository


class TrainingJobRepository(BaseRepository[TrainingJob]):
    """Async repository for `TrainingJob`."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=TrainingJob)

    async def create(self, job: TrainingJob) -> TrainingJob:
        """Persist a new training job. Caller is responsible for committing."""
        return await self.add(job)

    async def get_by_id(self, job_id: UUID) -> TrainingJob | None:
        """Fetch a single training job by its UUID primary key."""
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
        """Return non-deleted training jobs for a specific user with pagination."""
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
        """Return the total number of non-deleted jobs for a user.

        Used for pagination total in list_jobs.
        """
        stmt = select(func.count(TrainingJob.id)).where(
            TrainingJob.user_id == user_id,
            TrainingJob.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0

    async def count_active_jobs(self, user_id: UUID) -> int:
        """Return the number of ACTIVE (QUEUED or RUNNING) jobs for a user.

        Used to enforce the "1 active job per user" constraint.
        """
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
        """Update the status of a training job.

        Optionally set started_at and/or completed_at timestamps.
        Returns the updated job, or None if not found.
        """
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

    async def update_artifact_path(
        self, job_id: UUID, artifact_path: str
    ) -> TrainingJob | None:
        """Set the artifact path on a completed training job.

        Returns the updated job, or None if not found.
        """
        job = await self.get_by_id(job_id)
        if job is None:
            return None
        job.artifact_path = artifact_path
        await self._session.flush()
        await self._session.refresh(job)
        return job

    async def update_error(
        self, job_id: UUID, error_message: str
    ) -> TrainingJob | None:
        """Set the error message on a failed training job.

        Also sets completed_at to now and status to FAILED.
        Returns the updated job, or None if not found.
        """
        job = await self.get_by_id(job_id)
        if job is None:
            return None
        job.status = TrainingJobStatus.FAILED
        job.error_message = error_message
        job.completed_at = datetime.now(timezone.utc)
        await self._session.flush()
        await self._session.refresh(job)
        return job
