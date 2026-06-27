"""Model Registry repository.

Encapsulates all database access for `Model` and `ModelVersion`.
Business logic lives in the service layer, not here.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model import Model, ModelVersion, ModelVersionStatus
from app.repositories.base import BaseRepository


class ModelRepository(BaseRepository[Model]):
    """Async repository for `Model` and `ModelVersion`."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=Model)

    # ------------------------------------------------------------------
    # Model operations
    # ------------------------------------------------------------------

    async def create_model(self, model: Model) -> Model:
        """Persist a new model. Caller commits."""
        return await self.add(model)

    async def get_model(self, model_id: UUID) -> Model | None:
        """Fetch a single model by UUID with versions loaded."""
        result = await self._session.execute(
            select(Model).where(Model.id == model_id)
        )
        return result.scalar_one_or_none()

    async def list_models(
        self,
        owner_id: UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Model]:
        """Return models for an owner, newest first."""
        stmt = (
            select(Model)
            .where(Model.owner_id == owner_id)
            .order_by(Model.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_models(self, owner_id: UUID) -> int:
        """Total models for an owner (pagination total)."""
        stmt = select(func.count(Model.id)).where(Model.owner_id == owner_id)
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0

    # ------------------------------------------------------------------
    # Version operations
    # ------------------------------------------------------------------

    async def get_version(self, version_id: UUID) -> ModelVersion | None:
        """Fetch a single model version by UUID."""
        result = await self._session.execute(
            select(ModelVersion).where(ModelVersion.id == version_id)
        )
        return result.scalar_one_or_none()

    async def get_version_by_number(
        self, model_id: UUID, version_number: int
    ) -> ModelVersion | None:
        """Fetch a version by its model + version number."""
        result = await self._session.execute(
            select(ModelVersion).where(
                ModelVersion.model_id == model_id,
                ModelVersion.version_number == version_number,
            )
        )
        return result.scalar_one_or_none()

    async def get_next_version_number(self, model_id: UUID) -> int:
        """Return the next version number for a model (1 if none exist)."""
        stmt = select(func.max(ModelVersion.version_number)).where(
            ModelVersion.model_id == model_id
        )
        result = await self._session.execute(stmt)
        max_number = result.scalar_one()
        return (max_number or 0) + 1

    async def create_version(self, version: ModelVersion) -> ModelVersion:
        """Persist a new model version. Caller commits."""
        return await self.add(version)

    async def get_current_production_version(
        self, model_id: UUID
    ) -> ModelVersion | None:
        """Return the current PRODUCTION version for a model, if any."""
        result = await self._session.execute(
            select(ModelVersion).where(
                ModelVersion.model_id == model_id,
                ModelVersion.status == ModelVersionStatus.PRODUCTION,
            )
        )
        return result.scalar_one_or_none()

    async def promote_version(
        self,
        version_id: UUID,
    ) -> ModelVersion | None:
        """Atomically promote a version to PRODUCTION.

        Demotes any existing PRODUCTION version of the same model to
        STAGING in the same transaction. Returns the promoted version,
        or None if not found.
        """
        version = await self.get_version(version_id)
        if version is None:
            return None

        current_prod = await self.get_current_production_version(
            version.model_id
        )
        if current_prod is not None and current_prod.id != version.id:
            current_prod.status = ModelVersionStatus.STAGING

        version.status = ModelVersionStatus.PRODUCTION
        await self._session.flush()
        await self._session.refresh(version)
        if current_prod is not None and current_prod.id != version.id:
            await self._session.refresh(current_prod)
        return version

    async def archive_version(self, version_id: UUID) -> ModelVersion | None:
        """Mark a version as ARCHIVED. Returns the version or None."""
        version = await self.get_version(version_id)
        if version is None:
            return None
        version.status = ModelVersionStatus.ARCHIVED
        await self._session.flush()
        await self._session.refresh(version)
        return version
