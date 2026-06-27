"""Training job API routes.

Endpoints:
- POST   /training-jobs           — Create a training job.
- GET    /training-jobs           — List training jobs for current user.
- GET    /training-jobs/{id}      — Get a training job by ID.
- POST   /training-jobs/{id}/cancel — Cancel a training job.

Phase 3.2:
- All endpoints enforce ownership at the service layer.
- Only one ACTIVE (QUEUED or RUNNING) job per user at a time.
- Dataset ownership is validated before job creation.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DBSession
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.training_job_repository import TrainingJobRepository
from app.schemas.common import SuccessResponse
from app.schemas.training_job import (
    TrainingJobCreateRequest,
    TrainingJobListResponse,
    TrainingJobResponse,
)
from app.services.queue_service import QueueService
from app.services.training_service import (
    ActiveJobLimitExceededError,
    DatasetNotOwnedError,
    TrainingJobAccessDeniedError,
    TrainingJobNotCancellableError,
    TrainingJobNotFoundError,
    TrainingService,
)

router = APIRouter(prefix="/training-jobs", tags=["training-jobs"])


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------


def _get_training_service(
    db: DBSession,
) -> TrainingService:
    """Build a TrainingService with all its dependencies."""
    return TrainingService(
        job_repo=TrainingJobRepository(db),
        dataset_repo=DatasetRepository(db),
        queue_service=QueueService(),
    )


TrainingServiceDep = Annotated[TrainingService, Depends(_get_training_service)]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=SuccessResponse[TrainingJobResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a training job",
)
async def create_training_job(
    current_user: CurrentUser,
    service: TrainingServiceDep,
    request: TrainingJobCreateRequest,
) -> SuccessResponse[TrainingJobResponse]:
    """Create a new training job.

    Validates:
    - The dataset is owned by the current user.
    - The user has no other ACTIVE (QUEUED or RUNNING) jobs.

    On success the job is enqueued for background execution.
    """
    result = await service.create_job(
        user_id=current_user.id,
        request=request,
    )
    return SuccessResponse(success=True, data=result)


@router.get(
    "",
    response_model=SuccessResponse[TrainingJobListResponse],
    summary="List training jobs",
)
async def list_training_jobs(
    current_user: CurrentUser,
    service: TrainingServiceDep,
    limit: Annotated[
        int,
        Query(ge=1, le=500, description="Max items per page"),
    ] = 100,
    offset: Annotated[
        int,
        Query(ge=0, description="Number of items to skip"),
    ] = 0,
) -> SuccessResponse[TrainingJobListResponse]:
    """Return a paginated list of training jobs for the current user."""
    result = await service.list_jobs(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return SuccessResponse(success=True, data=result)


@router.get(
    "/{job_id}",
    response_model=SuccessResponse[TrainingJobResponse],
    summary="Get a training job",
)
async def get_training_job(
    current_user: CurrentUser,
    service: TrainingServiceDep,
    job_id: UUID,
) -> SuccessResponse[TrainingJobResponse]:
    """Return a single training job by ID.

    Only the job owner can view it.
    """
    result = await service.get_job(
        job_id,
        user_id=current_user.id,
    )
    return SuccessResponse(success=True, data=result)


@router.post(
    "/{job_id}/cancel",
    response_model=SuccessResponse[TrainingJobResponse],
    summary="Cancel a training job",
)
async def cancel_training_job(
    current_user: CurrentUser,
    service: TrainingServiceDep,
    job_id: UUID,
) -> SuccessResponse[TrainingJobResponse]:
    """Cancel a training job.

    Only QUEUED or RUNNING jobs can be cancelled.
    """
    result = await service.cancel_job(
        job_id,
        user_id=current_user.id,
    )
    return SuccessResponse(success=True, data=result)
