"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1 import auth, datasets, deployments, evaluations, health, models, training_jobs

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(datasets.router)
api_router.include_router(training_jobs.router)
api_router.include_router(evaluations.router)
api_router.include_router(models.router)
api_router.include_router(deployments.router)
