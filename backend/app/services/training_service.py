"""Training service.

Orchestrates training job creation, queueing, querying, and
cancellation. This is the business-logic layer between API routes
and the repository / queue service.

Per approved revisions:
- No CREATED status — jobs start as QUEUED.
- No execution_target / PENDING_COLAB.
- Enforce 1 ACTIVE (QUEUED or RUNNING) job per user.
- TrainingConfig has exactly 4 fields: epochs, batch_size,
  learning_rate, max_seq_length.
- MockTrainingRunner replaces real training infrastructure.
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


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class TrainingJobError(Exception):
    """Base exception for training-job-related errors."""


class TrainingJobNotFoundError(TrainingJobError):
    """Raised when a training job does not exist."""

    def __init__(self, job_id: UUID) -> None:
        self.job_id = job_id
        super().__init__(f"Training job not found: {job_id}")


class TrainingJobAccessDeniedError(TrainingJobError):
    """Raised when a user attempts to access a job they do not own."""

    def __init__(self, job_id: UUID) -> None:
        self.job_id = job_id
        super().__init__(f"Access to training job {job_id} is denied.")


class ActiveJobLimitExceededError(TrainingJobError):
    """Raised when a user already has an active (QUEUED or RUNNING) job."""

    def __init__(self, user_id: UUID) -> None:
        self.user_id = user_id
        super().__init__(
            f"User {user_id} already has an active training job. "
            "Only one active job is allowed at a time."
        )


class DatasetNotOwnedError(TrainingJobError):
    """Raised when a user tries to create a job with a dataset they don't own."""

    def __init__(self, dataset_id: UUID, user_id: UUID) -> None:
        self.dataset_id = dataset_id
        self.user_id = user_id
        super().__init__(
            f"Dataset {dataset_id} is not owned by user {user_id}."
        )


class TrainingJobNotCancellableError(TrainingJobError):
    """Raised when a job cannot be cancelled (not in QUEUED or RUNNING status)."""

    def __init__(self, job_id: UUID, status: TrainingJobStatus) -> None:
        self.job_id = job_id
        self.status = status
        super().__init__(
            f"Training job {job_id} cannot be cancelled because its "
            f"status is '{status.value}', not 'queued' or 'running'."
        )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class TrainingService:
    """Business logic for training job management."""

    def __init__(
        self,
        job_repo: TrainingJobRepository,
        dataset_repo: DatasetRepository,
        queue_service: QueueService,
    ) -> None:
        self._jobs = job_repo
        self._datasets = dataset_repo
        self._queue = queue_service

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_job(
        self,
        *,
        user_id: UUID,
        request: TrainingJobCreateRequest,
    ) -> TrainingJobResponse:
        """Create a new training job and enqueue it.

        Workflow:
        1. Validate that the user owns the referenced dataset.
        2. Check that the user has no active (QUEUED/RUNNING) jobs.
        3. Create the TrainingJob row (status=QUEUED).
        4. Enqueue the job via QueueService.
        5. Commit and return.
        """
        # 1. Dataset ownership check
        dataset = await self._datasets.get_by_id_and_owner(
            request.dataset_id, user_id
        )
        if dataset is None:
            raise DatasetNotOwnedError(request.dataset_id, user_id)

        # 2. Active job limit check
        active_count = await self._jobs.count_active_jobs(user_id)
        if active_count >= 1:
            raise ActiveJobLimitExceededError(user_id)

        # 3. Create job row
        job = TrainingJob(
            user_id=user_id,
            dataset_id=request.dataset_id,
            dataset_version_id=request.dataset_version_id,
            base_model=request.base_model,
            training_type=request.training_type,
            configuration=request.configuration.model_dump(),
        )
        job = await self._jobs.create(job)

        # 4. Enqueue
        self._queue.enqueue(job.id)

        # 5. Commit — catch IntegrityError from the partial unique index
        #    (uq_one_active_job_per_user) which enforces one active job
        #    per user at the database level. This closes the TOCTOU race
        #    between the count check above and the INSERT.
        try:
            await self._jobs.commit()
        except IntegrityError as exc:
            await self._jobs.session.rollback()
            raise ActiveJobLimitExceededError(user_id) from exc

        await self._jobs.session.refresh(job)

        return TrainingJobResponse.model_validate(job)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get_job(
        self, job_id: UUID, *, user_id: UUID
    ) -> TrainingJobResponse:
        """Return a single training job.

        Raises TrainingJobAccessDeniedError if the job does not belong
        to the requesting user.
        """
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
        """Return a paginated list of training jobs for a user."""
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

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------

    async def cancel_job(
        self, job_id: UUID, *, user_id: UUID
    ) -> TrainingJobResponse:
        """Cancel a training job.

        Only QUEUED or RUNNING jobs can be cancelled.
        - If QUEUED: cancel the RQ job, then update status to CANCELLED.
        - If RUNNING: update status to CANCELLED (the mock runner will
          detect this on its next check).
        Raises TrainingJobAccessDeniedError if the job doesn't belong to
        the requesting user.
        Raises TrainingJobNotCancellableError if the job is not in a
        cancellable state.
        """
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

        # If QUEUED, try to cancel the RQ job
        if job.status == TrainingJobStatus.QUEUED:
            self._queue.cancel_queued_job(job_id)

        # Update status
        updated = await self._jobs.update_status(
            job_id,
            TrainingJobStatus.CANCELLED,
            completed_at=datetime.now(timezone.utc),
        )
        await self._jobs.commit()

        if updated is None:
            raise TrainingJobNotFoundError(job_id)

        return TrainingJobResponse.model_validate(updated)
