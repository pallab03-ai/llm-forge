"""Local filesystem storage for uploaded dataset files.

Replaces MinIO. Files live under
``{LOCAL_STORAGE_PATH}/datasets/{dataset_id}/{version_number}/{filename}``.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from app.core.config import settings


class StorageError(Exception):
    """Raised when a storage operation fails."""


class LocalStorageService:
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
        target_dir = self._dataset_dir(dataset_id, version_number)
        target_dir.mkdir(parents=True, exist_ok=True)

        file_path = target_dir / filename
        try:
            file_path.write_bytes(content)
        except OSError as exc:
            raise StorageError(
                f"Failed to write file {file_path}: {exc}"
            ) from exc

        return str(file_path.relative_to(self._root))

    def get_absolute_path(self, relative_path: str) -> Path:
        abs_path = (self._root / relative_path).resolve()
        # Ensure the resolved path is still under root (path-traversal guard).
        if not str(abs_path).startswith(str(self._root)):
            raise StorageError(
                f"Path traversal detected: {relative_path}"
            )
        return abs_path