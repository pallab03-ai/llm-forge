"""Health check endpoint."""

from fastapi import APIRouter

from app.core.config import settings
from app.schemas.common import HealthData, SuccessResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=SuccessResponse[HealthData])
async def health_check() -> SuccessResponse[HealthData]:
    data = HealthData(
        status="healthy",
        version=settings.APP_VERSION,
        environment=settings.APP_ENV,
    )
    return SuccessResponse(data=data)
