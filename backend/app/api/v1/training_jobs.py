"""Training job API routes.

Enforces ownership at the service layer; at most one ACTIVE (QUEUED
or RUNNING) job per user.
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


def _get_training_service(
    db: DBSession,
) -> TrainingService:
    return TrainingService(
        job_repo=TrainingJobRepository(db),
        dataset_repo=DatasetRepository(db),
        queue_service=QueueService(),
    )


TrainingServiceDep = Annotated[TrainingService, Depends(_get_training_service)]


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
    """Create and enqueue a new training job."""
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
    """Return a paginated list of the user's training jobs."""
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
    """Return a training job by ID (owner only)."""
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
    """Cancel a QUEUED or RUNNING job (owner only)."""
    result = await service.cancel_job(
        job_id,
        user_id=current_user.id,
    )
    return SuccessResponse(success=True, data=result)
