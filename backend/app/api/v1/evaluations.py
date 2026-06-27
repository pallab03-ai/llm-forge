"""Evaluation API routes.

Endpoints:
- POST   /evaluations          — Create + run an evaluation.
- GET    /evaluations          — List evaluations for current user.
- GET    /evaluations/{id}     — Get an evaluation by ID.

No DELETE endpoint (evaluations are immutable historical records).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DBSession
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.evaluation_repository import EvaluationRepository
from app.repositories.training_job_repository import TrainingJobRepository
from app.schemas.common import SuccessResponse
from app.schemas.evaluation import (
    EvaluationCreateRequest,
    EvaluationListResponse,
    EvaluationResponse,
)
from app.services.evaluation_service import EvaluationService

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------


def _get_evaluation_service(db: DBSession) -> EvaluationService:
    """Build an EvaluationService with all its dependencies."""
    return EvaluationService(
        evaluation_repo=EvaluationRepository(db),
        training_job_repo=TrainingJobRepository(db),
        dataset_repo=DatasetRepository(db),
    )


EvaluationServiceDep = Annotated[
    EvaluationService, Depends(_get_evaluation_service)
]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=SuccessResponse[EvaluationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create and run an evaluation",
)
async def create_evaluation(
    current_user: CurrentUser,
    service: EvaluationServiceDep,
    request: EvaluationCreateRequest,
) -> SuccessResponse[EvaluationResponse]:
    """Create a new evaluation and run it synchronously.

    Validates that the trained model (training job) exists, is owned by
    the current user, and has a completed adapter artifact. Validates
    dataset ownership. Computes ROUGE-L, BERTScore, and semantic
    similarity, then persists the results.
    """
    result = await service.create_evaluation(
        user_id=current_user.id,
        request=request,
    )
    return SuccessResponse(success=True, data=result)


@router.get(
    "",
    response_model=SuccessResponse[EvaluationListResponse],
    summary="List evaluations",
)
async def list_evaluations(
    current_user: CurrentUser,
    service: EvaluationServiceDep,
    limit: Annotated[
        int,
        Query(ge=1, le=500, description="Max items per page"),
    ] = 100,
    offset: Annotated[
        int,
        Query(ge=0, description="Number of items to skip"),
    ] = 0,
) -> SuccessResponse[EvaluationListResponse]:
    """Return a paginated list of evaluations for the current user."""
    result = await service.list_evaluations(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return SuccessResponse(success=True, data=result)


@router.get(
    "/{evaluation_id}",
    response_model=SuccessResponse[EvaluationResponse],
    summary="Get an evaluation",
)
async def get_evaluation(
    current_user: CurrentUser,
    service: EvaluationServiceDep,
    evaluation_id: UUID,
) -> SuccessResponse[EvaluationResponse]:
    """Return a single evaluation by ID. Only the owner can view it."""
    result = await service.get_evaluation(
        evaluation_id,
        user_id=current_user.id,
    )
    return SuccessResponse(success=True, data=result)
