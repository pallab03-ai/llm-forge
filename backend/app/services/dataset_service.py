"""Dataset service.

Orchestrates dataset upload, validation, versioning, listing, and
soft-delete. This is the business-logic layer between API routes and
repositories / storage / validation services.

Per approved revisions:
- LocalStorageService instead of MinIO.
- version_number is an integer.
- DatasetVersion.created_at is the upload timestamp.
- Duplicate detection only inside the uploaded file.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from app.core.config import settings
from app.models.dataset import (
    Dataset,
    DatasetFormat,
    DatasetStatus,
    DatasetType,
    DatasetVersion,
)
from app.repositories.dataset_repository import (
    DatasetRepository,
    DatasetVersionRepository,
)
from app.schemas.dataset import (
    DatasetDetailResponse,
    DatasetListResponse,
    DatasetResponse,
    DatasetStatisticsResponse,
    DatasetVersionResponse,
)
from app.services.storage_service import LocalStorageService, StorageError
from app.services.validation_service import ValidationResult, ValidationService


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class DatasetError(Exception):
    """Base exception for dataset-related errors."""


class DatasetNotFoundError(DatasetError):
    """Raised when a dataset does not exist."""

    def __init__(self, dataset_id: UUID) -> None:
        self.dataset_id = dataset_id
        super().__init__(f"Dataset not found: {dataset_id}")


class DatasetNameExistsError(DatasetError):
    """Raised when a dataset with the same name already exists."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Dataset with name '{name}' already exists.")


class DatasetValidationError(DatasetError):
    """Raised when a dataset file fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Validation failed: {', '.join(errors)}")


class DatasetVersionNotFoundError(DatasetError):
    """Raised when a dataset version does not exist."""

    def __init__(self, dataset_id: UUID, version_number: int) -> None:
        self.dataset_id = dataset_id
        self.version_number = version_number
        super().__init__(
            f"Version {version_number} not found for dataset {dataset_id}"
        )


class DatasetAccessDeniedError(DatasetError):
    """Raised when a user attempts to access a dataset they do not own.

    Phase 2.1: This is raised by the service layer when the requesting
    user is not the owner of the dataset. The API layer maps this to a
    403 Forbidden response. We deliberately do NOT distinguish between
    "dataset does not exist" and "dataset exists but you don't own it"
    in the response body — both surface as 403 to avoid leaking the
    existence of other users' datasets.
    """

    def __init__(self, dataset_id: UUID) -> None:
        self.dataset_id = dataset_id
        super().__init__(
            f"Access to dataset {dataset_id} is denied."
        )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class DatasetService:
    """Business logic for dataset management."""

    def __init__(
        self,
        dataset_repo: DatasetRepository,
        version_repo: DatasetVersionRepository,
        storage: LocalStorageService,
        validator: ValidationService,
    ) -> None:
        self._datasets = dataset_repo
        self._versions = version_repo
        self._storage = storage
        self._validator = validator

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    async def upload(
        self,
        *,
        name: str,
        dataset_type: DatasetType,
        format: DatasetFormat,
        file_content: bytes,
        filename: str,
        current_user_id: UUID,
        description: str | None = None,
    ) -> DatasetDetailResponse:
        """Upload a new dataset (creates dataset + version 1).

        Workflow:
        1. Check name uniqueness.
        2. Create Dataset row (status=uploading) owned by ``current_user_id``.
        3. Save file to local storage.
        4. Validate the file.
        5. Create DatasetVersion row.
        6. Update Dataset status to ready/failed.

        Phase 2.1: ``current_user_id`` is REQUIRED and is recorded as the
        dataset owner (``created_by``). All subsequent access checks use
        this field.
        """
        # 1. Name uniqueness
        if await self._datasets.name_exists(name):
            raise DatasetNameExistsError(name)

        # 2. Create dataset (owned by current_user_id)
        dataset = Dataset(
            name=name,
            description=description,
            dataset_type=dataset_type,
            format=format,
            status=DatasetStatus.UPLOADING,
            created_by=current_user_id,
        )
        await self._datasets.add(dataset)

        # 3. Save file
        version_number = 1
        try:
            relative_path = await self._storage.save_file(
                dataset_id=dataset.id,
                version_number=version_number,
                content=file_content,
                filename=filename,
            )
        except StorageError as exc:
            dataset.status = DatasetStatus.FAILED
            await self._datasets.commit()
            raise DatasetError(f"Failed to store file: {exc}") from exc

        # 4. Validate
        abs_path = self._storage.get_absolute_path(relative_path)
        validation = await self._validator.validate(
            file_path=abs_path,
            format=format,
            dataset_type=dataset_type,
        )

        # 5. Create version
        version = DatasetVersion(
            dataset_id=dataset.id,
            version_number=version_number,
            file_path=relative_path,
            file_size_bytes=len(file_content),
            record_count=validation.record_count,
            duplicate_count=validation.duplicate_count,
            validation_errors=(
                json.dumps(validation.errors)
                if validation.errors
                else None
            ),
            statistics=(
                json.dumps(validation.statistics)
                if validation.statistics
                else None
            ),
        )
        await self._versions.add(version)

        # 6. Update dataset status
        dataset.status = (
            DatasetStatus.READY if validation.is_valid else DatasetStatus.FAILED
        )
        await self._datasets.commit()
        # Phase 2.1: Refresh to load server-generated `updated_at` after
        # commit. Without this, Pydantic validation in
        # `_to_detail_response` triggers a lazy-load from a sync context,
        # raising `MissingGreenlet` in async sessions.
        await self._datasets.session.refresh(dataset)

        return self._to_detail_response(dataset, [version])

    # ------------------------------------------------------------------
    # Upload new version
    # ------------------------------------------------------------------

    async def upload_version(
        self,
        *,
        dataset_id: UUID,
        file_content: bytes,
        filename: str,
        current_user_id: UUID,
    ) -> DatasetDetailResponse:
        """Upload a new version of an existing dataset.

        Phase 2.1: ``current_user_id`` is REQUIRED. The dataset is loaded
        via ``get_by_id_and_owner`` so that a non-owner cannot upload a
        version to someone else's dataset. We raise
        ``DatasetAccessDeniedError`` (mapped to 403) rather than
        ``DatasetNotFoundError`` so the API layer can distinguish
        "doesn't exist" from "exists but not yours" — but the response
        body intentionally does not leak which case occurred.
        """
        dataset = await self._datasets.get_by_id_and_owner(
            dataset_id, current_user_id
        )
        if dataset is None:
            # Could be: doesn't exist, soft-deleted, or owned by someone
            # else. We surface 403 in all three cases to avoid leaking
            # existence of other users' datasets.
            raise DatasetAccessDeniedError(dataset_id)

        # Determine next version number
        latest = await self._versions.get_latest_version_number(dataset_id)
        version_number = latest + 1

        # Save file
        try:
            relative_path = await self._storage.save_file(
                dataset_id=dataset.id,
                version_number=version_number,
                content=file_content,
                filename=filename,
            )
        except StorageError as exc:
            raise DatasetError(f"Failed to store file: {exc}") from exc

        # Validate
        abs_path = self._storage.get_absolute_path(relative_path)
        validation = await self._validator.validate(
            file_path=abs_path,
            format=dataset.format,
            dataset_type=dataset.dataset_type,
        )

        # Create version
        version = DatasetVersion(
            dataset_id=dataset.id,
            version_number=version_number,
            file_path=relative_path,
            file_size_bytes=len(file_content),
            record_count=validation.record_count,
            duplicate_count=validation.duplicate_count,
            validation_errors=(
                json.dumps(validation.errors)
                if validation.errors
                else None
            ),
            statistics=(
                json.dumps(validation.statistics)
                if validation.statistics
                else None
            ),
        )
        await self._versions.add(version)

        # Update dataset status
        dataset.status = (
            DatasetStatus.READY if validation.is_valid else DatasetStatus.FAILED
        )
        await self._datasets.commit()
        # Phase 2.1: Refresh to load server-generated `updated_at` after
        # commit. See `upload()` for rationale.
        await self._datasets.session.refresh(dataset)

        # Reload versions
        versions = await self._versions.list_by_dataset(dataset.id)
        return self._to_detail_response(dataset, versions)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def list_datasets(
        self,
        *,
        current_user_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> DatasetListResponse:
        """Return a paginated list of active datasets owned by the user.

        Phase 2.1: Results are filtered to datasets owned by
        ``current_user_id``. Users only see their own datasets.
        """
        items = await self._datasets.list_active(
            owner_id=current_user_id, limit=limit, offset=offset
        )
        total = await self._datasets.count_active(owner_id=current_user_id)
        return DatasetListResponse(
            items=[self._to_response(d) for d in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_dataset(
        self, dataset_id: UUID, *, current_user_id: UUID
    ) -> DatasetDetailResponse:
        """Return a dataset with all its versions.

        Phase 2.1: Only the owner can read a dataset. Non-owners get
        ``DatasetAccessDeniedError`` (403).
        """
        dataset = await self._datasets.get_by_id_and_owner(
            dataset_id, current_user_id
        )
        if dataset is None:
            raise DatasetAccessDeniedError(dataset_id)
        versions = await self._versions.list_by_dataset(dataset.id)
        return self._to_detail_response(dataset, versions)

    async def get_versions(
        self, dataset_id: UUID, *, current_user_id: UUID
    ) -> list[DatasetVersionResponse]:
        """Return all versions for a dataset.

        Phase 2.1: Only the owner can list versions. Non-owners get
        ``DatasetAccessDeniedError`` (403).
        """
        dataset = await self._datasets.get_by_id_and_owner(
            dataset_id, current_user_id
        )
        if dataset is None:
            raise DatasetAccessDeniedError(dataset_id)
        versions = await self._versions.list_by_dataset(dataset.id)
        return [self._to_version_response(v) for v in versions]

    async def get_statistics(
        self, dataset_id: UUID, *, current_user_id: UUID
    ) -> DatasetStatisticsResponse:
        """Return aggregated statistics for a dataset.

        Phase 2.1: Only the owner can read statistics. Non-owners get
        ``DatasetAccessDeniedError`` (403).
        """
        dataset = await self._datasets.get_by_id_and_owner(
            dataset_id, current_user_id
        )
        if dataset is None:
            raise DatasetAccessDeniedError(dataset_id)
        versions = await self._versions.list_by_dataset(dataset.id)
        version_responses = [
            self._to_version_response(v) for v in versions
        ]
        return DatasetStatisticsResponse(
            dataset_id=dataset.id,
            dataset_name=dataset.name,
            total_versions=len(versions),
            latest_version=(
                versions[0].version_number if versions else None
            ),
            total_records=sum(v.record_count for v in versions),
            total_duplicates=sum(v.duplicate_count for v in versions),
            total_size_bytes=sum(v.file_size_bytes for v in versions),
            versions=version_responses,
        )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def soft_delete(
        self, dataset_id: UUID, *, current_user_id: UUID
    ) -> None:
        """Soft-delete a dataset.

        Phase 2.1: Only the owner can delete. Non-owners get
        ``DatasetAccessDeniedError`` (403).
        """
        deleted = await self._datasets.soft_delete(
            dataset_id, owner_id=current_user_id
        )
        if not deleted:
            # Either doesn't exist, already deleted, or not owned by
            # current_user. Surface as 403 to avoid leaking existence.
            raise DatasetAccessDeniedError(dataset_id)

    # ------------------------------------------------------------------
    # Response builders
    # ------------------------------------------------------------------

    @staticmethod
    def _to_response(dataset: Dataset) -> DatasetResponse:
        return DatasetResponse.model_validate(dataset)

    @staticmethod
    def _to_version_response(version: DatasetVersion) -> DatasetVersionResponse:
        return DatasetVersionResponse.model_validate(version)

    @staticmethod
    def _to_detail_response(
        dataset: Dataset, versions: list[DatasetVersion]
    ) -> DatasetDetailResponse:
        detail = DatasetDetailResponse.model_validate(dataset)
        detail.versions = [
            DatasetVersionResponse.model_validate(v) for v in versions
        ]
        return detail