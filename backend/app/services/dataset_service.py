"""Dataset service: upload, validate, version, list, soft-delete.

Owned by ``current_user_id``; access denied (403) when the caller
isn't the owner. Duplicate detection is within-file only.
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


class DatasetError(Exception):
    """Base exception for dataset errors."""


class DatasetNotFoundError(DatasetError):
    def __init__(self, dataset_id: UUID) -> None:
        self.dataset_id = dataset_id
        super().__init__(f"Dataset not found: {dataset_id}")


class DatasetNameExistsError(DatasetError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Dataset with name '{name}' already exists.")


class DatasetValidationError(DatasetError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Validation failed: {', '.join(errors)}")


class DatasetVersionNotFoundError(DatasetError):
    def __init__(self, dataset_id: UUID, version_number: int) -> None:
        self.dataset_id = dataset_id
        self.version_number = version_number
        super().__init__(
            f"Version {version_number} not found for dataset {dataset_id}"
        )


class DatasetAccessDeniedError(DatasetError):
    # Surfaces 403 for both "doesn't exist" and "exists but not yours"
    # so the response body never leaks which case it was.
    def __init__(self, dataset_id: UUID) -> None:
        self.dataset_id = dataset_id
        super().__init__(
            f"Access to dataset {dataset_id} is denied."
        )


class DatasetService:
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
        if await self._datasets.name_exists(name):
            raise DatasetNameExistsError(name)

        dataset = Dataset(
            name=name,
            description=description,
            dataset_type=dataset_type,
            format=format,
            status=DatasetStatus.UPLOADING,
            created_by=current_user_id,
        )
        await self._datasets.add(dataset)

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

        abs_path = self._storage.get_absolute_path(relative_path)
        validation = await self._validator.validate(
            file_path=abs_path,
            format=format,
            dataset_type=dataset_type,
        )

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

        dataset.status = (
            DatasetStatus.READY if validation.is_valid else DatasetStatus.FAILED
        )
        await self._datasets.commit()
        # Refresh so server-generated updated_at is loaded; otherwise
        # Pydantic validation in _to_detail_response triggers a
        # lazy-load from a sync context (MissingGreenlet in async).
        await self._datasets.session.refresh(dataset)

        return self._to_detail_response(dataset, [version])

    async def upload_version(
        self,
        *,
        dataset_id: UUID,
        file_content: bytes,
        filename: str,
        current_user_id: UUID,
    ) -> DatasetDetailResponse:
        dataset = await self._datasets.get_by_id_and_owner(
            dataset_id, current_user_id
        )
        if dataset is None:
            raise DatasetAccessDeniedError(dataset_id)

        latest = await self._versions.get_latest_version_number(dataset_id)
        version_number = latest + 1

        try:
            relative_path = await self._storage.save_file(
                dataset_id=dataset.id,
                version_number=version_number,
                content=file_content,
                filename=filename,
            )
        except StorageError as exc:
            raise DatasetError(f"Failed to store file: {exc}") from exc

        abs_path = self._storage.get_absolute_path(relative_path)
        validation = await self._validator.validate(
            file_path=abs_path,
            format=dataset.format,
            dataset_type=dataset.dataset_type,
        )

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

        dataset.status = (
            DatasetStatus.READY if validation.is_valid else DatasetStatus.FAILED
        )
        await self._datasets.commit()
        await self._datasets.session.refresh(dataset)

        versions = await self._versions.list_by_dataset(dataset.id)
        return self._to_detail_response(dataset, versions)

    async def list_datasets(
        self,
        *,
        current_user_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> DatasetListResponse:
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

    async def soft_delete(
        self, dataset_id: UUID, *, current_user_id: UUID
    ) -> None:
        deleted = await self._datasets.soft_delete(
            dataset_id, owner_id=current_user_id
        )
        if not deleted:
            # Doesn't exist, already deleted, or not the owner.
            raise DatasetAccessDeniedError(dataset_id)

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