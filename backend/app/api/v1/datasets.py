"""Dataset API routes.

Upload endpoints reject oversized payloads BEFORE reading them into
memory, using ``UploadFile.size`` (populated by Starlette from the
Content-Length header). Ownership is enforced at the service layer.
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
from app.repositories.dataset_repository import (
    DatasetRepository,
    DatasetVersionRepository,
)
from app.schemas.common import SuccessResponse
from app.schemas.dataset import (
    DatasetDetailResponse,
    DatasetListResponse,
    DatasetStatisticsResponse,
    DatasetVersionResponse,
)
from app.services.dataset_service import DatasetService
from app.services.storage_service import LocalStorageService
from app.services.validation_service import ValidationService

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _get_dataset_service(
    db: DBSession,
) -> DatasetService:
    return DatasetService(
        dataset_repo=DatasetRepository(db),
        version_repo=DatasetVersionRepository(db),
        storage=LocalStorageService(),
        validator=ValidationService(),
    )


DatasetServiceDep = Annotated[DatasetService, Depends(_get_dataset_service)]


def _reject_if_too_large(file: UploadFile) -> None:
    # OOM guard: Starlette populates ``file.size`` from Content-Length
    # when the client sends it. If the client uses chunked transfer
    # the size is None and we fall through to the service-layer check
    # after reading.
    max_bytes = settings.DATASET_MAX_FILE_SIZE_BYTES
    if file.size is not None and file.size > max_bytes:
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
    and size/record limits. The dataset is owned by ``current_user.id``.
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
    """Return a paginated list of active (non-deleted) datasets owned by the user."""
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
    """Return a dataset with all its versions (owner only)."""
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
    """Upload a new version of an existing dataset (owner only)."""
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
    """Return all versions for a dataset, newest first (owner only)."""
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
    """Return aggregated statistics across all versions (owner only)."""
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
    """Soft-delete a dataset (owner only)."""
    await service.soft_delete(
        dataset_id, current_user_id=current_user.id
    )
    return SuccessResponse(success=True, data=None)