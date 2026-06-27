"""Monitoring API routes.

Five endpoints, all behind JWT auth:

- ``GET /monitoring/dashboard``                — user-scoped aggregates
- ``GET /deployments/{id}/health``              — per-deployment health
- ``GET /deployments/{id}/metrics``             — per-deployment aggregates
- ``GET /deployments/{id}/requests``            — recent request log
- ``GET /deployments/{id}/errors``              — recent failed-request log
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, DBSession
from app.repositories.monitoring_repository import MonitoringRepository
from app.schemas.common import SuccessResponse
from app.schemas.monitoring import (
    DashboardResponse,
    DeploymentHealthResponse,
    DeploymentMetricsResponse,
    ErrorLogListResponse,
    RequestLogListResponse,
)
from app.services.monitoring_service import MonitoringService


router = APIRouter(tags=["monitoring"])


def _get_monitoring_service(db: DBSession) -> MonitoringService:
    return MonitoringService(MonitoringRepository(db))


MonitoringServiceDep = Annotated[
    MonitoringService, Depends(_get_monitoring_service)
]


@router.get(
    "/monitoring/dashboard",
    response_model=SuccessResponse[DashboardResponse],
    summary="User-scoped monitoring dashboard",
)
async def get_dashboard(
    current_user: CurrentUser,
    service: MonitoringServiceDep,
) -> SuccessResponse[DashboardResponse]:
    return SuccessResponse(
        success=True,
        data=await service.get_dashboard(user_id=current_user.id),
    )


@router.get(
    "/deployments/{deployment_id}/health",
    response_model=SuccessResponse[DeploymentHealthResponse],
    summary="Per-deployment health snapshot",
)
async def get_deployment_health(
    deployment_id: UUID,
    current_user: CurrentUser,
    service: MonitoringServiceDep,
) -> SuccessResponse[DeploymentHealthResponse]:
    return SuccessResponse(
        success=True,
        data=await service.get_health(
            deployment_id, user_id=current_user.id
        ),
    )


@router.get(
    "/deployments/{deployment_id}/metrics",
    response_model=SuccessResponse[DeploymentMetricsResponse],
    summary="Per-deployment aggregate metrics",
)
async def get_deployment_metrics(
    deployment_id: UUID,
    current_user: CurrentUser,
    service: MonitoringServiceDep,
) -> SuccessResponse[DeploymentMetricsResponse]:
    return SuccessResponse(
        success=True,
        data=await service.get_metrics(
            deployment_id, user_id=current_user.id
        ),
    )


@router.get(
    "/deployments/{deployment_id}/requests",
    response_model=SuccessResponse[RequestLogListResponse],
    summary="Recent request log for a deployment",
)
async def list_deployment_requests(
    deployment_id: UUID,
    current_user: CurrentUser,
    service: MonitoringServiceDep,
    limit: Annotated[
        int,
        Query(ge=1, le=500, description="Max items per page"),
    ] = 50,
    offset: Annotated[
        int,
        Query(ge=0, description="Number of items to skip"),
    ] = 0,
) -> SuccessResponse[RequestLogListResponse]:
    return SuccessResponse(
        success=True,
        data=await service.list_requests(
            deployment_id,
            user_id=current_user.id,
            limit=limit,
            offset=offset,
        ),
    )


@router.get(
    "/deployments/{deployment_id}/errors",
    response_model=SuccessResponse[ErrorLogListResponse],
    summary="Recent error log for a deployment",
)
async def list_deployment_errors(
    deployment_id: UUID,
    current_user: CurrentUser,
    service: MonitoringServiceDep,
    limit: Annotated[
        int,
        Query(ge=1, le=500, description="Max items per page"),
    ] = 50,
    offset: Annotated[
        int,
        Query(ge=0, description="Number of items to skip"),
    ] = 0,
) -> SuccessResponse[ErrorLogListResponse]:
    return SuccessResponse(
        success=True,
        data=await service.list_errors(
            deployment_id,
            user_id=current_user.id,
            limit=limit,
            offset=offset,
        ),
    )
