"""Local filesystem storage service.

Stores uploaded dataset files on the local filesystem under a
configurable root directory (LOCAL_STORAGE_PATH).

Per approved revision: replaces MinIO with simple local storage.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from uuid import UUID, uuid4

from app.core.config import settings


class StorageError(Exception):
    """Raised when a storage operation fails."""


class LocalStorageService:
    """Manages file storage on the local filesystem.

    Files are stored under::

        {LOCAL_STORAGE_PATH}/datasets/{dataset_id}/{version_number}/{filename}

    Usage::

        storage = LocalStorageService()
        path = await storage.save_file(dataset_id, version_number, content, filename)
    """

    def __init__(self, root_path: str | None = None) -> None:
        self._root = Path(root_path or settings.LOCAL_STORAGE_PATH).resolve()

    @property
    def root(self) -> Path:
        return self._root

    def _dataset_dir(self, dataset_id: UUID, version_number: int) -> Path:
        return self._root / "datasets" / str(dataset_id) / str(version_number)

    async def save_file(
        self,
        dataset_id: UUID,
        version_number: int,
        content: bytes,
        filename: str,
    ) -> str:
        """Save file bytes to local storage.

        Returns the relative path (from storage root) to the saved file.
        """
        target_dir = self._dataset_dir(dataset_id, version_number)
        target_dir.mkdir(parents=True, exist_ok=True)

        file_path = target_dir / filename
        try:
            file_path.write_bytes(content)
        except OSError as exc:
            raise StorageError(
                f"Failed to write file {file_path}: {exc}"
            ) from exc

        # Return path relative to storage root
        return str(file_path.relative_to(self._root))

    def get_absolute_path(self, relative_path: str) -> Path:
        """Resolve a relative storage path to an absolute filesystem path."""
        abs_path = (self._root / relative_path).resolve()
        # Safety: ensure the resolved path is still under root
        if not str(abs_path).startswith(str(self._root)):
            raise StorageError(
                f"Path traversal detected: {relative_path}"
            )
        return abs_path

    async def delete_file(self, relative_path: str) -> None:
        """Delete a file from local storage."""
        abs_path = self.get_absolute_path(relative_path)
        try:
            if abs_path.exists():
                abs_path.unlink()
        except OSError as exc:
            raise StorageError(
                f"Failed to delete file {abs_path}: {exc}"
            ) from exc

    async def delete_dataset_dir(self, dataset_id: UUID) -> None:
        """Remove the entire directory tree for a dataset."""
        dataset_dir = self._root / "datasets" / str(dataset_id)
        try:
            if dataset_dir.exists():
                shutil.rmtree(dataset_dir)
        except OSError as exc:
            raise StorageError(
                f"Failed to delete dataset dir {dataset_dir}: {exc}"
            ) from exc