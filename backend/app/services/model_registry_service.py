"""Model Registry service: model/version lifecycle.

create model → create version (register adapter) → promote → archive
"""

from __future__ import annotations

from uuid import UUID

from app.models.evaluation import Evaluation, EvaluationStatus
from app.models.model import Model, ModelVersion, ModelVersionStatus
from app.models.training_job import TrainingJob, TrainingJobStatus
from app.repositories.evaluation_repository import EvaluationRepository
from app.repositories.model_repository import ModelRepository
from app.repositories.training_job_repository import TrainingJobRepository
from app.schemas.model import (
    ModelCreateRequest,
    ModelListResponse,
    ModelResponse,
    ModelVersionCreateRequest,
    ModelVersionResponse,
)


class ModelRegistryError(Exception):
    """Base exception for model registry errors."""

    code = "MODEL_REGISTRY_ERROR"
    http_status = 400


class ModelNotFoundError(ModelRegistryError):
    """Raised when a model does not exist or is not accessible."""

    code = "MODEL_NOT_FOUND"
    http_status = 404

    def __init__(self, model_id: UUID) -> None:
        self.model_id = model_id
        super().__init__(f"Model not found: {model_id}")


class ModelAccessDeniedError(ModelRegistryError):
    """Raised when a user accesses a model they do not own."""

    code = "MODEL_ACCESS_DENIED"
    http_status = 403

    def __init__(self, model_id: UUID) -> None:
        self.model_id = model_id
        super().__init__(f"Access to model {model_id} is denied.")


class ModelVersionNotFoundError(ModelRegistryError):
    """Raised when a model version does not exist."""

    code = "MODEL_VERSION_NOT_FOUND"
    http_status = 404

    def __init__(self, version_id: UUID) -> None:
        self.version_id = version_id
        super().__init__(f"Model version not found: {version_id}")


class ModelVersionAccessDeniedError(ModelRegistryError):
    """Raised when a user accesses a version they do not own."""

    code = "MODEL_VERSION_ACCESS_DENIED"
    http_status = 403

    def __init__(self, version_id: UUID) -> None:
        self.version_id = version_id
        super().__init__(f"Access to model version {version_id} is denied.")


class ModelVersionExistsError(ModelRegistryError):
    """Raised when a duplicate version number would be created."""

    code = "MODEL_VERSION_EXISTS"
    http_status = 409

    def __init__(self, model_id: UUID, version_number: int) -> None:
        self.model_id = model_id
        self.version_number = version_number
        super().__init__(
            f"Model {model_id} already has version {version_number}."
        )


class TrainingJobNotFoundError(ModelRegistryError):
    """Raised when the referenced training job does not exist."""

    code = "TRAINING_JOB_NOT_FOUND"
    http_status = 404

    def __init__(self, job_id: UUID) -> None:
        self.job_id = job_id
        super().__init__(f"Training job not found: {job_id}")


class TrainingJobNotReadyError(ModelRegistryError):
    """Raised when the training job has not completed or has no artifact."""

    code = "TRAINING_JOB_NOT_READY"
    http_status = 409

    def __init__(self, job_id: UUID) -> None:
        self.job_id = job_id
        super().__init__(
            f"Training job {job_id} is not completed or has no artifact."
        )


class EvaluationNotFoundError(ModelRegistryError):
    """Raised when the referenced evaluation does not exist."""

    code = "EVALUATION_NOT_FOUND"
    http_status = 404

    def __init__(self, evaluation_id: UUID) -> None:
        self.evaluation_id = evaluation_id
        super().__init__(f"Evaluation not found: {evaluation_id}")


class EvaluationNotReadyError(ModelRegistryError):
    """Raised when the evaluation is not completed."""

    code = "EVALUATION_NOT_READY"
    http_status = 409

    def __init__(self, evaluation_id: UUID) -> None:
        self.evaluation_id = evaluation_id
        super().__init__(f"Evaluation {evaluation_id} is not completed.")


class InvalidPromotionError(ModelRegistryError):
    """Raised when a version cannot be promoted."""

    code = "INVALID_PROMOTION"
    http_status = 409

    def __init__(self, version_id: UUID, reason: str) -> None:
        self.version_id = version_id
        super().__init__(f"Cannot promote version {version_id}: {reason}")


class InvalidArchiveError(ModelRegistryError):
    """Raised when a version cannot be archived."""

    code = "INVALID_ARCHIVE"
    http_status = 409

    def __init__(self, version_id: UUID, reason: str) -> None:
        self.version_id = version_id
        super().__init__(f"Cannot archive version {version_id}: {reason}")


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ModelRegistryService:
    """Business logic for model registry management."""

    def __init__(
        self,
        model_repo: ModelRepository,
        training_job_repo: TrainingJobRepository,
        evaluation_repo: EvaluationRepository,
    ) -> None:
        self._models = model_repo
        self._jobs = training_job_repo
        self._evals = evaluation_repo

    async def create_model(
        self,
        *,
        user_id: UUID,
        request: ModelCreateRequest,
    ) -> ModelResponse:
        """Create a new model container."""
        model = Model(
            owner_id=user_id,
            name=request.name,
            description=request.description,
        )
        model = await self._models.create_model(model)
        await self._models.commit()
        return ModelResponse.model_validate(model)

    async def get_model(
        self,
        model_id: UUID,
        *,
        user_id: UUID,
    ) -> ModelResponse:
        """Return a model if owned by the user."""
        model = await self._models.get_model(model_id)
        if model is None:
            raise ModelNotFoundError(model_id)
        if model.owner_id != user_id:
            raise ModelAccessDeniedError(model_id)
        return ModelResponse.model_validate(model)

    async def list_models(
        self,
        *,
        user_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> ModelListResponse:
        """Return paginated models for a user."""
        items = await self._models.list_models(
            owner_id=user_id, limit=limit, offset=offset
        )
        total = await self._models.count_models(owner_id=user_id)
        return ModelListResponse(
            items=[ModelResponse.model_validate(m) for m in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def create_version(
        self,
        *,
        user_id: UUID,
        model_id: UUID,
        request: ModelVersionCreateRequest,
    ) -> ModelVersionResponse:
        """Register a trained adapter as a new version of a model.

        Validates:
        - model exists and is owned by user
        - training job exists, is owned by user, completed, has artifact
        - evaluation exists, is owned by user, completed
        - evaluation was for the same training job
        """
        model = await self._models.get_model(model_id)
        if model is None:
            raise ModelNotFoundError(model_id)
        if model.owner_id != user_id:
            raise ModelAccessDeniedError(model_id)

        job = await self._validate_training_job(
            request.training_job_id, user_id
        )
        evaluation = await self._validate_evaluation(
            request.evaluation_id, user_id
        )

        # Catch accidental cross-linking of unrelated jobs/evals.
        if evaluation.model_id != job.id:
            raise ModelRegistryError(
                f"Evaluation {evaluation.id} does not belong to "
                f"training job {job.id}."
            )

        version_number = await self._models.get_next_version_number(model_id)

        # Defensive: protect against races that could produce duplicate numbers
        existing = await self._models.get_version_by_number(
            model_id, version_number
        )
        if existing is not None:
            raise ModelVersionExistsError(model_id, version_number)

        version = ModelVersion(
            model_id=model_id,
            training_job_id=job.id,
            evaluation_id=evaluation.id,
            version_number=version_number,
            artifact_path=job.artifact_path,
            metrics_snapshot=self._build_metrics_snapshot(evaluation),
            status=ModelVersionStatus.STAGING,
        )
        version = await self._models.create_version(version)
        await self._models.commit()
        return ModelVersionResponse.model_validate(version)

    async def _validate_training_job(
        self, job_id: UUID, user_id: UUID
    ) -> TrainingJob:
        job = await self._jobs.get_by_id(job_id)
        if job is None or job.user_id != user_id:
            raise TrainingJobNotFoundError(job_id)
        if (
            job.status != TrainingJobStatus.COMPLETED
            or job.artifact_path is None
        ):
            raise TrainingJobNotReadyError(job_id)
        return job

    async def _validate_evaluation(
        self, evaluation_id: UUID, user_id: UUID
    ) -> Evaluation:
        evaluation = await self._evals.get_by_id(evaluation_id)
        if evaluation is None or evaluation.user_id != user_id:
            raise EvaluationNotFoundError(evaluation_id)
        if evaluation.status != EvaluationStatus.COMPLETED:
            raise EvaluationNotReadyError(evaluation_id)
        return evaluation

    def _build_metrics_snapshot(self, evaluation: Evaluation) -> dict:
        return {
            "rouge_score": evaluation.rouge_score,
            "bertscore_precision": evaluation.bertscore_precision,
            "bertscore_recall": evaluation.bertscore_recall,
            "bertscore_f1": evaluation.bertscore_f1,
            "semantic_similarity": evaluation.semantic_similarity,
        }

    async def promote_version(
        self,
        version_id: UUID,
        *,
        user_id: UUID,
    ) -> ModelVersionResponse:
        """Promote a version to PRODUCTION.

        Enforces:
        - version exists and is owned by user
        - version is not ARCHIVED
        - only one version per model is PRODUCTION (atomic demotion)
        """
        version = await self._ensure_version_access(version_id, user_id)

        if version.status == ModelVersionStatus.ARCHIVED:
            raise InvalidPromotionError(
                version_id, "archived versions cannot be promoted"
            )
        if version.status == ModelVersionStatus.PRODUCTION:
            raise InvalidPromotionError(
                version_id, "version is already in production"
            )

        promoted = await self._models.promote_version(version_id)
        if promoted is None:
            raise ModelVersionNotFoundError(version_id)
        await self._models.commit()
        return ModelVersionResponse.model_validate(promoted)

    async def archive_version(
        self,
        version_id: UUID,
        *,
        user_id: UUID,
    ) -> ModelVersionResponse:
        """Archive a version.

        Enforces:
        - version exists and is owned by user
        - version is not already archived (idempotent would be acceptable,
          but strict is clearer)
        """
        version = await self._ensure_version_access(version_id, user_id)

        if version.status == ModelVersionStatus.ARCHIVED:
            raise InvalidArchiveError(
                version_id, "version is already archived"
            )

        archived = await self._models.archive_version(version_id)
        if archived is None:
            raise ModelVersionNotFoundError(version_id)
        await self._models.commit()
        return ModelVersionResponse.model_validate(archived)

    async def _ensure_version_access(
        self, version_id: UUID, user_id: UUID
    ) -> ModelVersion:
        version = await self._models.get_version(version_id)
        if version is None:
            raise ModelVersionNotFoundError(version_id)
        model = await self._models.get_model(version.model_id)
        if model is None or model.owner_id != user_id:
            raise ModelVersionAccessDeniedError(version_id)
        return version
