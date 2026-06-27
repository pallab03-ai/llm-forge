"""Deployment API routes.

Endpoints:
- POST /deployments                    — Create a deployment.
- GET  /deployments                    — List deployments for current user.
- GET  /deployments/{id}               — Get a deployment by ID.
- POST /deployments/{id}/activate      — Load adapter and activate.
- POST /deployments/{id}/generate      — Run inference.

No DELETE endpoints.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DBSession
from app.repositories.deployment_repository import DeploymentRepository
from app.repositories.model_repository import ModelRepository
from app.repositories.training_job_repository import TrainingJobRepository
from app.schemas.common import SuccessResponse
from app.schemas.deployment import (
    DeploymentCreateRequest,
    DeploymentListResponse,
    DeploymentResponse,
    GenerateRequest,
    GenerateResponse,
)
from app.services.deployment_service import DeploymentService
from app.services.inference_service import InferenceService

router = APIRouter(prefix="/deployments", tags=["deployments"])

# ponytail: module-level singleton so the loaded model is reused across
# requests. Tests can monkeypatch this instance or override the dependency.
_inference_service = InferenceService()


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------


def _get_deployment_service(db: DBSession) -> DeploymentService:
    """Build a DeploymentService with request-scoped repos and shared inference."""
    return DeploymentService(
        deployment_repo=DeploymentRepository(db),
        model_repo=ModelRepository(db),
        training_job_repo=TrainingJobRepository(db),
        inference_service=_inference_service,
    )


DeploymentServiceDep = Annotated[
    DeploymentService, Depends(_get_deployment_service)
]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=SuccessResponse[DeploymentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a deployment",
)
async def create_deployment(
    current_user: CurrentUser,
    service: DeploymentServiceDep,
    request: DeploymentCreateRequest,
) -> SuccessResponse[DeploymentResponse]:
    """Create a new deployment for a ModelVersion."""
    result = await service.create_deployment(
        user_id=current_user.id,
        request=request,
    )
    return SuccessResponse(success=True, data=result)


@router.get(
    "",
    response_model=SuccessResponse[DeploymentListResponse],
    summary="List deployments",
)
async def list_deployments(
    current_user: CurrentUser,
    service: DeploymentServiceDep,
    limit: Annotated[
        int,
        Query(ge=1, le=500, description="Max items per page"),
    ] = 100,
    offset: Annotated[
        int,
        Query(ge=0, description="Number of items to skip"),
    ] = 0,
) -> SuccessResponse[DeploymentListResponse]:
    """Return a paginated list of deployments for the current user."""
    result = await service.list_deployments(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return SuccessResponse(success=True, data=result)


@router.get(
    "/{deployment_id}",
    response_model=SuccessResponse[DeploymentResponse],
    summary="Get a deployment",
)
async def get_deployment(
    current_user: CurrentUser,
    service: DeploymentServiceDep,
    deployment_id: UUID,
) -> SuccessResponse[DeploymentResponse]:
    """Return a single deployment by ID. Only the owner can view it."""
    result = await service.get_deployment(
        deployment_id,
        user_id=current_user.id,
    )
    return SuccessResponse(success=True, data=result)


@router.post(
    "/{deployment_id}/activate",
    response_model=SuccessResponse[DeploymentResponse],
    summary="Activate a deployment",
)
async def activate_deployment(
    current_user: CurrentUser,
    service: DeploymentServiceDep,
    deployment_id: UUID,
) -> SuccessResponse[DeploymentResponse]:
    """Load the adapter and mark the deployment as ACTIVE."""
    result = await service.activate_deployment(
        deployment_id,
        user_id=current_user.id,
    )
    return SuccessResponse(success=True, data=result)


@router.post(
    "/{deployment_id}/generate",
    response_model=SuccessResponse[GenerateResponse],
    summary="Generate text from a deployment",
)
async def generate(
    current_user: CurrentUser,
    service: DeploymentServiceDep,
    deployment_id: UUID,
    request: GenerateRequest,
) -> SuccessResponse[GenerateResponse]:
    """Run inference against an ACTIVE deployment."""
    result = await service.generate(
        deployment_id,
        user_id=current_user.id,
        request=request,
    )
    return SuccessResponse(success=True, data=result)
