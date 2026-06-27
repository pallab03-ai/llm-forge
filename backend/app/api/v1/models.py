"""Model Registry API routes.

Endpoints:
- POST  /models                    — Create a model container.
- GET   /models                    — List models for current user.
- GET   /models/{id}               — Get a model by ID.
- POST  /models/{id}/versions      — Register a trained adapter as a version.
- POST  /models/versions/{id}/promote — Promote a version to PRODUCTION.
- POST  /models/versions/{id}/archive — Archive a version.

No DELETE endpoints (versions move to ARCHIVED).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DBSession
from app.repositories.evaluation_repository import EvaluationRepository
from app.repositories.model_repository import ModelRepository
from app.repositories.training_job_repository import TrainingJobRepository
from app.schemas.common import SuccessResponse
from app.schemas.model import (
    ModelCreateRequest,
    ModelListResponse,
    ModelResponse,
    ModelVersionCreateRequest,
    ModelVersionResponse,
)
from app.services.model_registry_service import ModelRegistryService

router = APIRouter(prefix="/models", tags=["models"])


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------


def _get_model_registry_service(db: DBSession) -> ModelRegistryService:
    """Build a ModelRegistryService with all its dependencies."""
    return ModelRegistryService(
        model_repo=ModelRepository(db),
        training_job_repo=TrainingJobRepository(db),
        evaluation_repo=EvaluationRepository(db),
    )


ModelRegistryServiceDep = Annotated[
    ModelRegistryService, Depends(_get_model_registry_service)
]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=SuccessResponse[ModelResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a model",
)
async def create_model(
    current_user: CurrentUser,
    service: ModelRegistryServiceDep,
    request: ModelCreateRequest,
) -> SuccessResponse[ModelResponse]:
    """Create a new model container in the registry."""
    result = await service.create_model(
        user_id=current_user.id,
        request=request,
    )
    return SuccessResponse(success=True, data=result)


@router.get(
    "",
    response_model=SuccessResponse[ModelListResponse],
    summary="List models",
)
async def list_models(
    current_user: CurrentUser,
    service: ModelRegistryServiceDep,
    limit: Annotated[
        int,
        Query(ge=1, le=500, description="Max items per page"),
    ] = 100,
    offset: Annotated[
        int,
        Query(ge=0, description="Number of items to skip"),
    ] = 0,
) -> SuccessResponse[ModelListResponse]:
    """Return a paginated list of models for the current user."""
    result = await service.list_models(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return SuccessResponse(success=True, data=result)


@router.get(
    "/{model_id}",
    response_model=SuccessResponse[ModelResponse],
    summary="Get a model",
)
async def get_model(
    current_user: CurrentUser,
    service: ModelRegistryServiceDep,
    model_id: UUID,
) -> SuccessResponse[ModelResponse]:
    """Return a single model by ID. Only the owner can view it."""
    result = await service.get_model(
        model_id,
        user_id=current_user.id,
    )
    return SuccessResponse(success=True, data=result)


@router.post(
    "/{model_id}/versions",
    response_model=SuccessResponse[ModelVersionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a model version",
)
async def create_version(
    current_user: CurrentUser,
    service: ModelRegistryServiceDep,
    model_id: UUID,
    request: ModelVersionCreateRequest,
) -> SuccessResponse[ModelVersionResponse]:
    """Register a trained adapter as a new version of a model.

    Validates that the training job is completed, has an artifact, and
    that the evaluation is completed and belongs to the same adapter.
    """
    result = await service.create_version(
        user_id=current_user.id,
        model_id=model_id,
        request=request,
    )
    return SuccessResponse(success=True, data=result)


@router.post(
    "/versions/{version_id}/promote",
    response_model=SuccessResponse[ModelVersionResponse],
    summary="Promote a model version",
)
async def promote_version(
    current_user: CurrentUser,
    service: ModelRegistryServiceDep,
    version_id: UUID,
) -> SuccessResponse[ModelVersionResponse]:
    """Promote a version to PRODUCTION.

    Any existing PRODUCTION version of the same model is automatically
    demoted to STAGING in the same transaction.
    """
    result = await service.promote_version(
        version_id,
        user_id=current_user.id,
    )
    return SuccessResponse(success=True, data=result)


@router.post(
    "/versions/{version_id}/archive",
    response_model=SuccessResponse[ModelVersionResponse],
    summary="Archive a model version",
)
async def archive_version(
    current_user: CurrentUser,
    service: ModelRegistryServiceDep,
    version_id: UUID,
) -> SuccessResponse[ModelVersionResponse]:
    """Archive a model version."""
    result = await service.archive_version(
        version_id,
        user_id=current_user.id,
    )
    return SuccessResponse(success=True, data=result)
