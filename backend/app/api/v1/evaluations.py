"""Evaluation API routes.

Evaluations are immutable historical records — no DELETE endpoint.
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


def _get_evaluation_service(db: DBSession) -> EvaluationService:
    return EvaluationService(
        evaluation_repo=EvaluationRepository(db),
        training_job_repo=TrainingJobRepository(db),
        dataset_repo=DatasetRepository(db),
    )


EvaluationServiceDep = Annotated[
    EvaluationService, Depends(_get_evaluation_service)
]


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
    """Create and run a new evaluation (ROUGE-L, BERTScore, semantic similarity)."""
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
    """Return a paginated list of the user's evaluations."""
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
    """Return an evaluation by ID (owner only)."""
    result = await service.get_evaluation(
        evaluation_id,
        user_id=current_user.id,
    )
    return SuccessResponse(success=True, data=result)
