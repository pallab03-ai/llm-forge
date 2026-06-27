"""Deployment service.

Orchestrates the deployment lifecycle:
  create deployment → validate ModelVersion → activate → load adapter → ACTIVE

Business rules live here. Repositories provide raw data access.
"""

from __future__ import annotations

from uuid import UUID

from app.models.deployment import Deployment, DeploymentStatus
from app.models.model import ModelVersion, ModelVersionStatus
from app.models.training_job import TrainingJob
from app.repositories.deployment_repository import DeploymentRepository
from app.repositories.model_repository import ModelRepository
from app.repositories.training_job_repository import TrainingJobRepository
from app.schemas.deployment import (
    DeploymentCreateRequest,
    DeploymentListResponse,
    DeploymentResponse,
    GenerateRequest,
    GenerateResponse,
)
from app.services.inference_service import InferenceError, InferenceService


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class DeploymentError(Exception):
    """Base exception for deployment-related errors."""

    code = "DEPLOYMENT_ERROR"
    http_status = 400


class DeploymentNotFoundError(DeploymentError):
    """Raised when a deployment does not exist."""

    code = "DEPLOYMENT_NOT_FOUND"
    http_status = 404

    def __init__(self, deployment_id: UUID) -> None:
        self.deployment_id = deployment_id
        super().__init__(f"Deployment not found: {deployment_id}")


class DeploymentAccessDeniedError(DeploymentError):
    """Raised when a user accesses a deployment they do not own."""

    code = "DEPLOYMENT_ACCESS_DENIED"
    http_status = 403

    def __init__(self, deployment_id: UUID) -> None:
        self.deployment_id = deployment_id
        super().__init__(f"Access to deployment {deployment_id} is denied.")


class DeploymentAlreadyActiveError(DeploymentError):
    """Raised when an active deployment already exists for the version."""

    code = "DEPLOYMENT_ALREADY_ACTIVE"
    http_status = 409

    def __init__(self, model_version_id: UUID) -> None:
        self.model_version_id = model_version_id
        super().__init__(
            f"An active deployment already exists for model version "
            f"{model_version_id}."
        )


class DeploymentModelVersionNotFoundError(DeploymentError):
    """Raised when the referenced model version does not exist or is not owned."""

    code = "MODEL_VERSION_NOT_FOUND"
    http_status = 404

    def __init__(self, version_id: UUID) -> None:
        self.version_id = version_id
        super().__init__(f"Model version not found: {version_id}")


class DeploymentModelVersionArchivedError(DeploymentError):
    """Raised when the referenced model version is archived."""

    code = "MODEL_VERSION_ARCHIVED"
    http_status = 409

    def __init__(self, version_id: UUID) -> None:
        self.version_id = version_id
        super().__init__(f"Model version {version_id} is archived.")


class DeploymentAdapterNotFoundError(DeploymentError):
    """Raised when the adapter artifact is missing on disk."""

    code = "ADAPTER_NOT_FOUND"
    http_status = 404

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"Adapter artifact not found at path: {path}")


class DeploymentNotActiveError(DeploymentError):
    """Raised when inference is requested on a non-ACTIVE deployment."""

    code = "DEPLOYMENT_NOT_ACTIVE"
    http_status = 409

    def __init__(self, deployment_id: UUID) -> None:
        self.deployment_id = deployment_id
        super().__init__(f"Deployment {deployment_id} is not active.")


class DeploymentInvalidStatusError(DeploymentError):
    """Raised when a deployment cannot transition from its current status."""

    code = "INVALID_DEPLOYMENT_STATUS"
    http_status = 409

    def __init__(self, deployment_id: UUID, reason: str) -> None:
        self.deployment_id = deployment_id
        super().__init__(
            f"Deployment {deployment_id} cannot change status: {reason}"
        )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class DeploymentService:
    """Business logic for managing deployments and inference."""

    def __init__(
        self,
        deployment_repo: DeploymentRepository,
        model_repo: ModelRepository,
        training_job_repo: TrainingJobRepository,
        inference_service: InferenceService,
    ) -> None:
        self._deployments = deployment_repo
        self._models = model_repo
        self._jobs = training_job_repo
        self._inference = inference_service

    # ------------------------------------------------------------------
    # Create + query
    # ------------------------------------------------------------------

    async def create_deployment(
        self,
        *,
        user_id: UUID,
        request: DeploymentCreateRequest,
    ) -> DeploymentResponse:
        """Create a new deployment for a ModelVersion.

        Validates:
        - version exists and is owned by the user
        - version is not archived
        - no active deployment already exists for this version
        """
        version = await self._models.get_version(request.model_version_id)
        await self._ensure_version_owned(
            version, request.model_version_id, user_id
        )

        if version.status == ModelVersionStatus.ARCHIVED:
            raise DeploymentModelVersionArchivedError(version.id)

        active = await self._deployments.find_active_deployment(
            owner_id=user_id,
            model_version_id=version.id,
        )
        if active is not None:
            raise DeploymentAlreadyActiveError(version.id)

        deployment = Deployment(
            owner_id=user_id,
            model_version_id=version.id,
            deployment_name=request.deployment_name,
            endpoint_name=request.endpoint_name,
            status=DeploymentStatus.PENDING,
        )
        deployment = await self._deployments.create_deployment(deployment)
        await self._deployments.commit()
        return DeploymentResponse.model_validate(deployment)

    async def get_deployment(
        self,
        deployment_id: UUID,
        *,
        user_id: UUID,
    ) -> DeploymentResponse:
        """Return a deployment if owned by the user."""
        deployment = await self._ensure_deployment_access(deployment_id, user_id)
        return DeploymentResponse.model_validate(deployment)

    async def list_deployments(
        self,
        *,
        user_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> DeploymentListResponse:
        """Return paginated deployments for a user."""
        items = await self._deployments.list_deployments(
            owner_id=user_id, limit=limit, offset=offset
        )
        total = await self._deployments.count_deployments(owner_id=user_id)
        return DeploymentListResponse(
            items=[DeploymentResponse.model_validate(d) for d in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def activate_deployment(
        self,
        deployment_id: UUID,
        *,
        user_id: UUID,
    ) -> DeploymentResponse:
        """Activate a deployment by loading its adapter into the inference engine.

        Flow:
        1. Validate deployment is PENDING or FAILED.
        2. Validate the model version is still deployable.
        3. Validate the adapter exists on disk.
        4. Set DEPLOYING, load the model, then set ACTIVE.
        5. On load failure, set FAILED and raise.
        """
        import os

        deployment = await self._ensure_deployment_access(deployment_id, user_id)

        if deployment.status == DeploymentStatus.ACTIVE:
            raise DeploymentAlreadyActiveError(deployment.model_version_id)
        if deployment.status not in (
            DeploymentStatus.PENDING,
            DeploymentStatus.FAILED,
        ):
            raise DeploymentInvalidStatusError(
                deployment.id,
                "only PENDING or FAILED deployments can be activated",
            )

        version = await self._models.get_version(deployment.model_version_id)
        await self._ensure_version_owned(
            version, deployment.model_version_id, user_id
        )

        if version.status == ModelVersionStatus.ARCHIVED:
            raise DeploymentModelVersionArchivedError(version.id)

        job = await self._jobs.get_by_id(version.training_job_id)
        artifact_path = self._resolve_artifact_path(version, job)
        if not os.path.isdir(artifact_path):
            raise DeploymentAdapterNotFoundError(artifact_path)

        deployment.status = DeploymentStatus.DEPLOYING
        await self._deployments.update_status(
            deployment, DeploymentStatus.DEPLOYING
        )

        try:
            base_model = job.base_model if job is not None else ""
            self._inference.load(artifact_path, base_model)
        except InferenceError as exc:
            await self._deployments.update_status(
                deployment, DeploymentStatus.FAILED
            )
            await self._deployments.commit()
            raise DeploymentError(f"Failed to load model: {exc}") from exc

        deployment = await self._deployments.update_status(
            deployment, DeploymentStatus.ACTIVE
        )
        await self._deployments.commit()
        return DeploymentResponse.model_validate(deployment)

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    async def generate(
        self,
        deployment_id: UUID,
        *,
        user_id: UUID,
        request: GenerateRequest,
    ) -> GenerateResponse:
        """Run inference against an ACTIVE deployment."""
        deployment = await self._ensure_deployment_access(deployment_id, user_id)

        if deployment.status != DeploymentStatus.ACTIVE:
            raise DeploymentNotActiveError(deployment.id)

        version = await self._models.get_version(deployment.model_version_id)
        job = await self._jobs.get_by_id(version.training_job_id)
        artifact_path = self._resolve_artifact_path(version, job)
        base_model = job.base_model if job is not None else ""

        # ponytail: lazily (re)load if the process restarted or the cache
        # was cleared. Activation already loads, so this is a safety net.
        self._inference.load(artifact_path, base_model)

        try:
            response = self._inference.generate(request.prompt)
        except InferenceError as exc:
            raise DeploymentError(f"Inference failed: {exc}") from exc

        return GenerateResponse(response=response)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _ensure_deployment_access(
        self, deployment_id: UUID, user_id: UUID
    ) -> Deployment:
        """Fetch a deployment and verify ownership."""
        deployment = await self._deployments.get_deployment(deployment_id)
        if deployment is None:
            raise DeploymentNotFoundError(deployment_id)
        if deployment.owner_id != user_id:
            raise DeploymentAccessDeniedError(deployment_id)
        return deployment

    async def _ensure_version_owned(
        self,
        version: ModelVersion | None,
        version_id: UUID,
        user_id: UUID,
    ) -> None:
        """Ensure a model version exists and belongs to the user."""
        if version is None:
            raise DeploymentModelVersionNotFoundError(version_id)
        model = await self._models.get_model(version.model_id)
        if model is None or model.owner_id != user_id:
            raise DeploymentModelVersionNotFoundError(version_id)

    def _resolve_artifact_path(
        self, version, job: TrainingJob | None
    ) -> str:
        """Return the on-disk adapter path for a model version."""
        if job is not None and job.artifact_path:
            return job.artifact_path
        return version.artifact_path
