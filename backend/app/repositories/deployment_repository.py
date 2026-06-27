"""Deployment repository.

Encapsulates all database access for `Deployment`.
Business logic lives in the service layer, not here.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deployment import Deployment, DeploymentStatus
from app.repositories.base import BaseRepository


class DeploymentRepository(BaseRepository[Deployment]):
    """Async repository for `Deployment`."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=Deployment)

    async def create_deployment(self, deployment: Deployment) -> Deployment:
        """Persist a new deployment. Caller commits."""
        return await self.add(deployment)

    async def get_deployment(self, deployment_id: UUID) -> Deployment | None:
        """Fetch a single deployment by UUID."""
        return await self.get_by_id(deployment_id)

    async def list_deployments(
        self,
        owner_id: UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Deployment]:
        """Return deployments for an owner, newest first."""
        stmt = (
            select(Deployment)
            .where(Deployment.owner_id == owner_id)
            .order_by(Deployment.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_deployments(self, owner_id: UUID) -> int:
        """Total deployments for an owner (pagination total)."""
        stmt = select(func.count(Deployment.id)).where(
            Deployment.owner_id == owner_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0

    async def update_status(
        self,
        deployment: Deployment,
        status: DeploymentStatus,
    ) -> Deployment:
        """Set a deployment's status and flush. Caller commits."""
        deployment.status = status
        await self._session.flush()
        await self._session.refresh(deployment)
        return deployment

    async def find_active_deployment(
        self,
        *,
        owner_id: UUID | None = None,
        model_version_id: UUID | None = None,
    ) -> Deployment | None:
        """Return an ACTIVE deployment matching the filters, if any."""
        stmt = select(Deployment).where(
            Deployment.status == DeploymentStatus.ACTIVE
        )
        if owner_id is not None:
            stmt = stmt.where(Deployment.owner_id == owner_id)
        if model_version_id is not None:
            stmt = stmt.where(Deployment.model_version_id == model_version_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
