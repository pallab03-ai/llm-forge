"""Training job lifecycle: create, queue, query, cancel.

At most one ACTIVE (QUEUED/RUNNING) job per user. Jobs start at QUEUED
and end at COMPLETED/FAILED/CANCELLED.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.models.training_job import (
    TrainingJob,
    TrainingJobStatus,
    TrainingType,
)
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.training_job_repository import TrainingJobRepository
from app.schemas.training_job import (
    TrainingJobCreateRequest,
    TrainingJobListResponse,
    TrainingJobResponse,
)
from app.services.queue_service import QueueService


class TrainingJobError(Exception):
    """Base exception for training-job errors."""


class TrainingJobNotFoundError(TrainingJobError):
    def __init__(self, job_id: UUID) -> None:
        self.job_id = job_id
        super().__init__(f"Training job not found: {job_id}")


class TrainingJobAccessDeniedError(TrainingJobError):
    def __init__(self, job_id: UUID) -> None:
        self.job_id = job_id
        super().__init__(f"Access to training job {job_id} is denied.")


class ActiveJobLimitExceededError(TrainingJobError):
    def __init__(self, user_id: UUID) -> None:
        self.user_id = user_id
        super().__init__(
            f"User {user_id} already has an active training job. "
            "Only one active job is allowed at a time."
        )


class DatasetNotOwnedError(TrainingJobError):
    def __init__(self, dataset_id: UUID, user_id: UUID) -> None:
        self.dataset_id = dataset_id
        self.user_id = user_id
        super().__init__(
            f"Dataset {dataset_id} is not owned by user {user_id}."
        )


class TrainingJobNotCancellableError(TrainingJobError):
    def __init__(self, job_id: UUID, status: TrainingJobStatus) -> None:
        self.job_id = job_id
        self.status = status
        super().__init__(
            f"Training job {job_id} cannot be cancelled because its "
            f"status is '{status.value}', not 'queued' or 'running'."
        )


class TrainingService:
    def __init__(
        self,
        job_repo: TrainingJobRepository,
        dataset_repo: DatasetRepository,
        queue_service: QueueService,
    ) -> None:
        self._jobs = job_repo
        self._datasets = dataset_repo
        self._queue = queue_service

    async def create_job(
        self,
        *,
        user_id: UUID,
        request: TrainingJobCreateRequest,
    ) -> TrainingJobResponse:
        dataset = await self._datasets.get_by_id_and_owner(
            request.dataset_id, user_id
        )
        if dataset is None:
            raise DatasetNotOwnedError(request.dataset_id, user_id)

        if await self._jobs.count_active_jobs(user_id) >= 1:
            raise ActiveJobLimitExceededError(user_id)

        job = TrainingJob(
            user_id=user_id,
            dataset_id=request.dataset_id,
            dataset_version_id=request.dataset_version_id,
            base_model=request.base_model,
            training_type=request.training_type,
            configuration=request.configuration.model_dump(),
        )
        job = await self._jobs.create(job)

        self._queue.enqueue(job.id)

        # The DB-level unique-active index closes the TOCTOU race
        # between the count check above and this INSERT.
        try:
            await self._jobs.commit()
        except IntegrityError as exc:
            await self._jobs.session.rollback()
            raise ActiveJobLimitExceededError(user_id) from exc

        await self._jobs.session.refresh(job)

        return TrainingJobResponse.model_validate(job)

    async def get_job(
        self, job_id: UUID, *, user_id: UUID
    ) -> TrainingJobResponse:
        job = await self._jobs.get_by_id(job_id)
        if job is None:
            raise TrainingJobNotFoundError(job_id)
        if job.user_id != user_id:
            raise TrainingJobAccessDeniedError(job_id)
        return TrainingJobResponse.model_validate(job)

    async def list_jobs(
        self,
        *,
        user_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> TrainingJobListResponse:
        items = await self._jobs.list_for_user(
            user_id, limit=limit, offset=offset
        )
        total = await self._jobs.count_for_user(user_id)
        return TrainingJobListResponse(
            items=[TrainingJobResponse.model_validate(j) for j in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def cancel_job(
        self, job_id: UUID, *, user_id: UUID
    ) -> TrainingJobResponse:
        job = await self._jobs.get_by_id(job_id)
        if job is None:
            raise TrainingJobNotFoundError(job_id)
        if job.user_id != user_id:
            raise TrainingJobAccessDeniedError(job_id)

        if job.status not in (
            TrainingJobStatus.QUEUED,
            TrainingJobStatus.RUNNING,
        ):
            raise TrainingJobNotCancellableError(job_id, job.status)

        if job.status == TrainingJobStatus.QUEUED:
            self._queue.cancel_queued_job(job_id)

        updated = await self._jobs.update_status(
            job_id,
            TrainingJobStatus.CANCELLED,
            completed_at=datetime.now(timezone.utc),
        )
        await self._jobs.commit()

        if updated is None:
            raise TrainingJobNotFoundError(job_id)

        return TrainingJobResponse.model_validate(updated)
