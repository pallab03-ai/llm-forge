"""Dataset API routes.

Endpoints:
- POST   /datasets              — Upload a new dataset (v1).
- GET    /datasets              — List datasets.
- GET    /datasets/{id}         — Get dataset detail with versions.
- POST   /datasets/{id}/versions — Upload a new version.
- GET    /datasets/{id}/versions — List versions.
- GET    /datasets/{id}/statistics — Aggregated statistics.
- DELETE /datasets/{id}         — Soft-delete a dataset.

Phase 2.1 security:
- All endpoints enforce ownership at the service layer. Non-owners
  receive 403 (DatasetAccessDeniedError).
- Upload endpoints reject files larger than
  ``settings.DATASET_MAX_FILE_SIZE_BYTES`` BEFORE reading the file
  into memory, using ``UploadFile.size`` (which Starlette populates
  from the Content-Length header). This prevents OOM on oversized
  uploads.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)

from app.api.deps import CurrentUser, DBSession
from app.core.config import settings
from app.models.dataset import DatasetFormat, DatasetType
from app.models.user import User
from app.repositories.dataset_repository import (
    DatasetRepository,
    DatasetVersionRepository,
)
from app.schemas.common import ErrorDetail, ErrorResponse, SuccessResponse
from app.schemas.dataset import (
    DatasetDetailResponse,
    DatasetListResponse,
    DatasetStatisticsResponse,
    DatasetVersionResponse,
)
from app.services.dataset_service import (
    DatasetAccessDeniedError,
    DatasetError,
    DatasetNameExistsError,
    DatasetNotFoundError,
    DatasetService,
    DatasetValidationError,
    DatasetVersionNotFoundError,
)
from app.services.storage_service import LocalStorageService
from app.services.validation_service import ValidationService

router = APIRouter(prefix="/datasets", tags=["datasets"])


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------


def _get_dataset_service(
    db: DBSession,
) -> DatasetService:
    """Build a DatasetService with all its dependencies."""
    return DatasetService(
        dataset_repo=DatasetRepository(db),
        version_repo=DatasetVersionRepository(db),
        storage=LocalStorageService(),
        validator=ValidationService(),
    )


DatasetServiceDep = Annotated[DatasetService, Depends(_get_dataset_service)]


# ---------------------------------------------------------------------------
# Exception handlers (registered in main.py)
# ---------------------------------------------------------------------------


async def dataset_error_handler(
    request, exc: DatasetError
) -> ErrorResponse:
    """Map DatasetError → 400."""
    return ErrorResponse(
        success=False,
        error=ErrorDetail(
            code="DATASET_ERROR",
            message=str(exc),
        ),
    )


async def dataset_not_found_handler(
    request, exc: DatasetNotFoundError
) -> ErrorResponse:
    """Map DatasetNotFoundError → 404."""
    return ErrorResponse(
        success=False,
        error=ErrorDetail(
            code="DATASET_NOT_FOUND",
            message=str(exc),
        ),
    )


async def dataset_name_exists_handler(
    request, exc: DatasetNameExistsError
) -> ErrorResponse:
    """Map DatasetNameExistsError → 409."""
    return ErrorResponse(
        success=False,
        error=ErrorDetail(
            code="DATASET_NAME_EXISTS",
            message=str(exc),
        ),
    )


async def dataset_validation_error_handler(
    request, exc: DatasetValidationError
) -> ErrorResponse:
    """Map DatasetValidationError → 422."""
    return ErrorResponse(
        success=False,
        error=ErrorDetail(
            code="DATASET_VALIDATION_FAILED",
            message=str(exc),
        ),
    )


async def dataset_access_denied_handler(
    request, exc: DatasetAccessDeniedError
) -> ErrorResponse:
    """Map DatasetAccessDeniedError → 403.

    Phase 2.1: We deliberately do NOT distinguish between "dataset does
    not exist" and "dataset exists but you don't own it" in the
    response body — both surface as 403 to avoid leaking the existence
    of other users' datasets.
    """
    return ErrorResponse(
        success=False,
        error=ErrorDetail(
            code="DATASET_ACCESS_DENIED",
            message="You do not have access to this dataset.",
        ),
    )


# ---------------------------------------------------------------------------
# Upload helpers
# ---------------------------------------------------------------------------


def _reject_if_too_large(file: UploadFile) -> None:
    """Reject an upload BEFORE reading it into memory.

    Phase 2.1: ``UploadFile.size`` is populated by Starlette from the
    Content-Length header when the client sends it. We use it as a
    cheap pre-check so we never ``await file.read()`` a multi-GB
    payload into process memory.

    If the client omits Content-Length (chunked transfer), ``size`` is
    ``None`` and we fall through to the service-layer check after
    reading. The service-layer check is the authoritative one; this
    pre-check is purely an OOM guard.
    """
    max_bytes = settings.DATASET_MAX_FILE_SIZE_BYTES
    if file.size is not None and file.size > max_bytes:
        # Raise a plain HTTPException with a structured detail payload
        # so the global error envelope is consistent with the rest of
        # the API. FastAPI will serialize ``detail`` as JSON.
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={
                "code": "DATASET_FILE_TOO_LARGE",
                "message": (
                    f"File is {file.size} bytes which exceeds the maximum "
                    f"allowed size of {max_bytes} bytes "
                    f"({max_bytes // (1024 * 1024)} MB)."
                ),
            },
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=SuccessResponse[DatasetDetailResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new dataset",
)
async def upload_dataset(
    db: DBSession,
    current_user: CurrentUser,
    service: DatasetServiceDep,
    file: Annotated[
        UploadFile,
        File(description="Dataset file (CSV, JSON, or JSONL)"),
    ],
    name: Annotated[
        str,
        Form(description="Dataset name"),
    ],
    dataset_type: Annotated[
        DatasetType,
        Form(description="Dataset type: instruction_tuning, chat, or qa"),
    ],
    format: Annotated[
        DatasetFormat,
        Form(description="File format: csv, json, or jsonl"),
    ],
    description: Annotated[
        str | None,
        Form(description="Optional description"),
    ] = None,
) -> SuccessResponse[DatasetDetailResponse]:
    """Upload a dataset file and create version 1.

    The file is validated for schema correctness, duplicates (within-file),
    and size/record limits. On success the dataset status is `ready`;
    on validation failure it is `failed`.

    Phase 2.1: oversized files are rejected with 413 BEFORE being read
    into memory. The dataset is owned by ``current_user.id``.
    """
    _reject_if_too_large(file)
    content = await file.read()
    filename = file.filename or "dataset"

    result = await service.upload(
        name=name,
        dataset_type=dataset_type,
        format=format,
        file_content=content,
        filename=filename,
        description=description,
        current_user_id=current_user.id,
    )
    return SuccessResponse(success=True, data=result)


@router.get(
    "",
    response_model=SuccessResponse[DatasetListResponse],
    summary="List datasets",
)
async def list_datasets(
    db: DBSession,
    current_user: CurrentUser,
    service: DatasetServiceDep,
    limit: Annotated[
        int,
        Query(ge=1, le=500, description="Max items per page"),
    ] = 100,
    offset: Annotated[
        int,
        Query(ge=0, description="Number of items to skip"),
    ] = 0,
) -> SuccessResponse[DatasetListResponse]:
    """Return a paginated list of active (non-deleted) datasets.

    Phase 2.1: only datasets owned by the current user are returned.
    """
    result = await service.list_datasets(
        current_user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return SuccessResponse(success=True, data=result)


@router.get(
    "/{dataset_id}",
    response_model=SuccessResponse[DatasetDetailResponse],
    summary="Get dataset detail",
)
async def get_dataset(
    db: DBSession,
    current_user: CurrentUser,
    service: DatasetServiceDep,
    dataset_id: UUID,
) -> SuccessResponse[DatasetDetailResponse]:
    """Return a dataset with all its versions.

    Phase 2.1: only the owner can read a dataset. Non-owners get 403.
    """
    result = await service.get_dataset(
        dataset_id, current_user_id=current_user.id
    )
    return SuccessResponse(success=True, data=result)


@router.post(
    "/{dataset_id}/versions",
    response_model=SuccessResponse[DatasetDetailResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new dataset version",
)
async def upload_dataset_version(
    db: DBSession,
    current_user: CurrentUser,
    service: DatasetServiceDep,
    dataset_id: UUID,
    file: Annotated[
        UploadFile,
        File(description="Dataset file for the new version"),
    ],
) -> SuccessResponse[DatasetDetailResponse]:
    """Upload a new version of an existing dataset.

    The version number is auto-incremented. The file is validated
    against the dataset's type and format.

    Phase 2.1: oversized files are rejected with 413 BEFORE being read
    into memory. Only the dataset owner can upload a new version.
    """
    _reject_if_too_large(file)
    content = await file.read()
    filename = file.filename or "dataset"

    result = await service.upload_version(
        dataset_id=dataset_id,
        file_content=content,
        filename=filename,
        current_user_id=current_user.id,
    )
    return SuccessResponse(success=True, data=result)


@router.get(
    "/{dataset_id}/versions",
    response_model=SuccessResponse[list[DatasetVersionResponse]],
    summary="List dataset versions",
)
async def list_dataset_versions(
    db: DBSession,
    current_user: CurrentUser,
    service: DatasetServiceDep,
    dataset_id: UUID,
) -> SuccessResponse[list[DatasetVersionResponse]]:
    """Return all versions for a dataset, newest first.

    Phase 2.1: only the owner can list versions.
    """
    result = await service.get_versions(
        dataset_id, current_user_id=current_user.id
    )
    return SuccessResponse(success=True, data=result)


@router.get(
    "/{dataset_id}/statistics",
    response_model=SuccessResponse[DatasetStatisticsResponse],
    summary="Get dataset statistics",
)
async def get_dataset_statistics(
    db: DBSession,
    current_user: CurrentUser,
    service: DatasetServiceDep,
    dataset_id: UUID,
) -> SuccessResponse[DatasetStatisticsResponse]:
    """Return aggregated statistics across all versions.

    Phase 2.1: only the owner can read statistics.
    """
    result = await service.get_statistics(
        dataset_id, current_user_id=current_user.id
    )
    return SuccessResponse(success=True, data=result)


@router.delete(
    "/{dataset_id}",
    response_model=SuccessResponse[None],
    summary="Soft-delete a dataset",
)
async def delete_dataset(
    db: DBSession,
    current_user: CurrentUser,
    service: DatasetServiceDep,
    dataset_id: UUID,
) -> SuccessResponse[None]:
    """Soft-delete a dataset (sets deleted_at, status=deleted).

    Phase 2.1: only the owner can delete.
    """
    await service.soft_delete(
        dataset_id, current_user_id=current_user.id
    )
    return SuccessResponse(success=True, data=None)