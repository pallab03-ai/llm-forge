"""FastAPI application entry point.

Phase 0 — Foundation only. Wires up:
- Structured logging
- CORS middleware
- API v1 router (health endpoint)
- OpenAPI documentation

Phase 1 — Adds:
- Custom exception handlers that emit the standard
  `{success, error}` envelope at the top level (not wrapped in `detail`).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.deps import MissingTokenError
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.services.auth_service import AuthError
from app.services.dataset_service import (
    DatasetAccessDeniedError,
    DatasetError,
    DatasetNameExistsError,
    DatasetNotFoundError,
    DatasetValidationError,
    DatasetVersionNotFoundError,
)
from app.services.training_service import (
    ActiveJobLimitExceededError,
    DatasetNotOwnedError,
    TrainingJobAccessDeniedError,
    TrainingJobError,
    TrainingJobNotCancellableError,
    TrainingJobNotFoundError,
)
from app.services.evaluation_service import (
    AdapterNotFoundError,
    DatasetNotFoundError as EvaluationDatasetNotFoundError,
    DatasetVersionNotFoundError as EvaluationDatasetVersionNotFoundError,
    EvaluationAccessDeniedError,
    EvaluationError,
    EvaluationNotFoundError,
    MetricComputationError,
    ModelNotFoundError,
    ModelNotReadyError,
)
from app.services.model_registry_service import (
    EvaluationNotFoundError as RegistryEvaluationNotFoundError,
    EvaluationNotReadyError as RegistryEvaluationNotReadyError,
    InvalidArchiveError,
    InvalidPromotionError,
    ModelAccessDeniedError,
    ModelNotFoundError as RegistryModelNotFoundError,
    ModelRegistryError,
    ModelVersionAccessDeniedError,
    ModelVersionExistsError,
    ModelVersionNotFoundError,
    TrainingJobNotFoundError as RegistryTrainingJobNotFoundError,
    TrainingJobNotReadyError as RegistryTrainingJobNotReadyError,
)
from app.services.deployment_service import (
    DeploymentAccessDeniedError,
    DeploymentAdapterNotFoundError,
    DeploymentAlreadyActiveError,
    DeploymentError,
    DeploymentInvalidStatusError,
    DeploymentModelVersionArchivedError,
    DeploymentModelVersionNotFoundError,
    DeploymentNotActiveError,
    DeploymentNotFoundError,
)
from app.services.inference_service import InferenceError


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    setup_logging()
    yield


def _envelope_error(*, code: str, message: str, http_status: int) -> JSONResponse:
    """Build a top-level `{success, error}` JSON response."""
    return JSONResponse(
        status_code=http_status,
        content={
            "success": False,
            "error": {"code": code, "message": message},
        },
    )


def create_app() -> FastAPI:
    """Application factory."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Exception handlers — emit the standard envelope at the top level.
    # ------------------------------------------------------------------

    @app.exception_handler(AuthError)
    async def _auth_error_handler(_: Request, exc: AuthError) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=exc.message,
            http_status=exc.http_status,
        )

    @app.exception_handler(MissingTokenError)
    async def _missing_token_handler(
        _: Request, exc: MissingTokenError
    ) -> JSONResponse:
        response = _envelope_error(
            code=exc.code,
            message=exc.message,
            http_status=exc.http_status,
        )
        response.headers["WWW-Authenticate"] = "Bearer"
        return response

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Keep FastAPI's default 422 status but expose the envelope shape
        # so clients can rely on a single error contract.
        # Sanitize errors: Pydantic's ctx may contain non-JSON-serializable
        # objects (e.g. ValueError instances from model_validator).  We
        # convert them to strings so the response can always be serialized.
        safe_errors = []
        for err in exc.errors():
            safe_err = {**err}
            if "ctx" in safe_err and isinstance(safe_err["ctx"], dict):
                safe_err["ctx"] = {
                    k: str(v) if not isinstance(v, (str, int, float, bool, type(None)))
                    else v
                    for k, v in safe_err["ctx"].items()
                }
            safe_errors.append(safe_err)

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "success": False,
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed",
                    "details": {"errors": safe_errors},
                },
            },
        )

    @app.exception_handler(DatasetAccessDeniedError)
    async def _dataset_access_denied_handler(
        _: Request, exc: DatasetAccessDeniedError
    ) -> JSONResponse:
        # Phase 2.1: 403 for cross-tenant access. We do NOT leak whether
        # the dataset exists — the message is intentionally generic.
        return _envelope_error(
            code="DATASET_ACCESS_DENIED",
            message="You do not have access to this dataset.",
            http_status=status.HTTP_403_FORBIDDEN,
        )

    @app.exception_handler(DatasetNotFoundError)
    async def _dataset_not_found_handler(
        _: Request, exc: DatasetNotFoundError
    ) -> JSONResponse:
        return _envelope_error(
            code="DATASET_NOT_FOUND",
            message=str(exc),
            http_status=status.HTTP_404_NOT_FOUND,
        )

    @app.exception_handler(DatasetNameExistsError)
    async def _dataset_name_exists_handler(
        _: Request, exc: DatasetNameExistsError
    ) -> JSONResponse:
        return _envelope_error(
            code="DATASET_NAME_EXISTS",
            message=str(exc),
            http_status=status.HTTP_409_CONFLICT,
        )

    @app.exception_handler(DatasetValidationError)
    async def _dataset_validation_error_handler(
        _: Request, exc: DatasetValidationError
    ) -> JSONResponse:
        return _envelope_error(
            code="DATASET_VALIDATION_FAILED",
            message=str(exc),
            http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    @app.exception_handler(DatasetVersionNotFoundError)
    async def _dataset_version_not_found_handler(
        _: Request, exc: DatasetVersionNotFoundError
    ) -> JSONResponse:
        return _envelope_error(
            code="DATASET_VERSION_NOT_FOUND",
            message=str(exc),
            http_status=status.HTTP_404_NOT_FOUND,
        )

    @app.exception_handler(DatasetError)
    async def _dataset_error_handler(
        _: Request, exc: DatasetError
    ) -> JSONResponse:
        return _envelope_error(
            code="DATASET_ERROR",
            message=str(exc),
            http_status=status.HTTP_400_BAD_REQUEST,
        )

    # -- Training job exception handlers (Phase 3) --

    @app.exception_handler(TrainingJobNotFoundError)
    async def _training_job_not_found_handler(
        _: Request, exc: TrainingJobNotFoundError
    ) -> JSONResponse:
        return _envelope_error(
            code="TRAINING_JOB_NOT_FOUND",
            message=str(exc),
            http_status=status.HTTP_404_NOT_FOUND,
        )

    @app.exception_handler(TrainingJobAccessDeniedError)
    async def _training_job_access_denied_handler(
        _: Request, exc: TrainingJobAccessDeniedError
    ) -> JSONResponse:
        return _envelope_error(
            code="TRAINING_JOB_ACCESS_DENIED",
            message="You do not have access to this training job.",
            http_status=status.HTTP_403_FORBIDDEN,
        )

    @app.exception_handler(ActiveJobLimitExceededError)
    async def _active_job_limit_exceeded_handler(
        _: Request, exc: ActiveJobLimitExceededError
    ) -> JSONResponse:
        return _envelope_error(
            code="ACTIVE_JOB_LIMIT_EXCEEDED",
            message=str(exc),
            http_status=status.HTTP_409_CONFLICT,
        )

    @app.exception_handler(DatasetNotOwnedError)
    async def _dataset_not_owned_handler(
        _: Request, exc: DatasetNotOwnedError
    ) -> JSONResponse:
        return _envelope_error(
            code="DATASET_NOT_OWNED",
            message="You do not own the specified dataset.",
            http_status=status.HTTP_403_FORBIDDEN,
        )

    @app.exception_handler(TrainingJobNotCancellableError)
    async def _training_job_not_cancellable_handler(
        _: Request, exc: TrainingJobNotCancellableError
    ) -> JSONResponse:
        return _envelope_error(
            code="TRAINING_JOB_NOT_CANCELLABLE",
            message=str(exc),
            http_status=status.HTTP_409_CONFLICT,
        )

    @app.exception_handler(TrainingJobError)
    async def _training_job_error_handler(
        _: Request, exc: TrainingJobError
    ) -> JSONResponse:
        return _envelope_error(
            code="TRAINING_JOB_ERROR",
            message=str(exc),
            http_status=status.HTTP_400_BAD_REQUEST,
        )

    # -- Evaluation exception handlers (Phase 5) --

    @app.exception_handler(EvaluationNotFoundError)
    async def _evaluation_not_found_handler(
        _: Request, exc: EvaluationNotFoundError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    @app.exception_handler(EvaluationAccessDeniedError)
    async def _evaluation_access_denied_handler(
        _: Request, exc: EvaluationAccessDeniedError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message="You do not have access to this evaluation.",
            http_status=exc.http_status,
        )

    @app.exception_handler(ModelNotFoundError)
    async def _model_not_found_handler(
        _: Request, exc: ModelNotFoundError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    @app.exception_handler(ModelNotReadyError)
    async def _model_not_ready_handler(
        _: Request, exc: ModelNotReadyError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    @app.exception_handler(EvaluationDatasetNotFoundError)
    async def _evaluation_dataset_not_found_handler(
        _: Request, exc: EvaluationDatasetNotFoundError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    @app.exception_handler(EvaluationDatasetVersionNotFoundError)
    async def _evaluation_dataset_version_not_found_handler(
        _: Request, exc: EvaluationDatasetVersionNotFoundError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    @app.exception_handler(AdapterNotFoundError)
    async def _adapter_not_found_handler(
        _: Request, exc: AdapterNotFoundError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    @app.exception_handler(MetricComputationError)
    async def _metric_computation_error_handler(
        _: Request, exc: MetricComputationError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    @app.exception_handler(EvaluationError)
    async def _evaluation_error_handler(
        _: Request, exc: EvaluationError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    # -- Model Registry exception handlers (Phase 6) --

    @app.exception_handler(RegistryModelNotFoundError)
    async def _registry_model_not_found_handler(
        _: Request, exc: RegistryModelNotFoundError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    @app.exception_handler(ModelAccessDeniedError)
    async def _model_access_denied_handler(
        _: Request, exc: ModelAccessDeniedError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message="You do not have access to this model.",
            http_status=exc.http_status,
        )

    @app.exception_handler(ModelVersionNotFoundError)
    async def _model_version_not_found_handler(
        _: Request, exc: ModelVersionNotFoundError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    @app.exception_handler(ModelVersionAccessDeniedError)
    async def _model_version_access_denied_handler(
        _: Request, exc: ModelVersionAccessDeniedError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message="You do not have access to this model version.",
            http_status=exc.http_status,
        )

    @app.exception_handler(ModelVersionExistsError)
    async def _model_version_exists_handler(
        _: Request, exc: ModelVersionExistsError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    @app.exception_handler(RegistryTrainingJobNotFoundError)
    async def _registry_training_job_not_found_handler(
        _: Request, exc: RegistryTrainingJobNotFoundError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    @app.exception_handler(RegistryTrainingJobNotReadyError)
    async def _registry_training_job_not_ready_handler(
        _: Request, exc: RegistryTrainingJobNotReadyError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    @app.exception_handler(RegistryEvaluationNotFoundError)
    async def _registry_evaluation_not_found_handler(
        _: Request, exc: RegistryEvaluationNotFoundError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    @app.exception_handler(RegistryEvaluationNotReadyError)
    async def _registry_evaluation_not_ready_handler(
        _: Request, exc: RegistryEvaluationNotReadyError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    @app.exception_handler(InvalidPromotionError)
    async def _invalid_promotion_handler(
        _: Request, exc: InvalidPromotionError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    @app.exception_handler(InvalidArchiveError)
    async def _invalid_archive_handler(
        _: Request, exc: InvalidArchiveError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    @app.exception_handler(ModelRegistryError)
    async def _model_registry_error_handler(
        _: Request, exc: ModelRegistryError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    # -- Deployment exception handlers (Phase 7) --

    @app.exception_handler(DeploymentNotFoundError)
    async def _deployment_not_found_handler(
        _: Request, exc: DeploymentNotFoundError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    @app.exception_handler(DeploymentAccessDeniedError)
    async def _deployment_access_denied_handler(
        _: Request, exc: DeploymentAccessDeniedError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message="You do not have access to this deployment.",
            http_status=exc.http_status,
        )

    @app.exception_handler(DeploymentModelVersionNotFoundError)
    async def _deployment_version_not_found_handler(
        _: Request, exc: DeploymentModelVersionNotFoundError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    @app.exception_handler(DeploymentModelVersionArchivedError)
    async def _deployment_version_archived_handler(
        _: Request, exc: DeploymentModelVersionArchivedError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    @app.exception_handler(DeploymentAlreadyActiveError)
    async def _deployment_already_active_handler(
        _: Request, exc: DeploymentAlreadyActiveError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    @app.exception_handler(DeploymentAdapterNotFoundError)
    async def _deployment_adapter_not_found_handler(
        _: Request, exc: DeploymentAdapterNotFoundError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    @app.exception_handler(DeploymentNotActiveError)
    async def _deployment_not_active_handler(
        _: Request, exc: DeploymentNotActiveError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    @app.exception_handler(DeploymentInvalidStatusError)
    async def _deployment_invalid_status_handler(
        _: Request, exc: DeploymentInvalidStatusError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    @app.exception_handler(InferenceError)
    async def _inference_error_handler(
        _: Request, exc: InferenceError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    @app.exception_handler(DeploymentError)
    async def _deployment_error_handler(
        _: Request, exc: DeploymentError
    ) -> JSONResponse:
        return _envelope_error(
            code=exc.code,
            message=str(exc),
            http_status=exc.http_status,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(
        _: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """Wrap any HTTPException in the standard `{success, error}` envelope.

        Phase 2.1: this lets route-level ``HTTPException`` raises (e.g.
        the upload size guard) participate in the same error contract
        as the rest of the API. If ``exc.detail`` is already a dict
        with ``code``/``message`` keys, we forward them verbatim;
        otherwise we synthesize a generic envelope.
        """
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail and "message" in detail:
            return _envelope_error(
                code=detail["code"],
                message=detail["message"],
                http_status=exc.status_code,
            )
        return _envelope_error(
            code=f"HTTP_{exc.status_code}",
            message=str(detail) if detail is not None else "HTTP error",
            http_status=exc.status_code,
        )

    # Mount API v1
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()
