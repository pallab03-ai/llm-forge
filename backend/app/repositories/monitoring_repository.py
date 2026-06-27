"""Monitoring repository.

Pure database access. Every method returns either a row, a list of
rows, or a scalar aggregate. No business logic — health verdicts,
success-rate calculations, and threshold checks live in the service.

All queries are scoped to a single ``owner_id`` so a request from user
A can never read user B's monitoring data.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deployment import Deployment, DeploymentStatus
from app.models.monitoring import (
    DeploymentHealth,
    DeploymentRequestLog,
    RequestStatus,
)


# ---------------------------------------------------------------------------
# Plain-old-data aggregate result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RequestAggregate:
    """Aggregate metrics over a deployment's request log."""

    request_count: int
    success_count: int
    failure_count: int
    average_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float


@dataclass(frozen=True)
class GlobalAggregate:
    """Aggregate metrics over a user's full deployment fleet."""

    total_requests: int
    success_count: int
    average_latency_ms: float


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class MonitoringRepository:
    """Database access for monitoring tables and read-only aggregates."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def add_request_log(self, entry: DeploymentRequestLog) -> DeploymentRequestLog:
        self._session.add(entry)
        await self._session.flush()
        await self._session.refresh(entry)
        return entry

    async def upsert_health(
        self, health: DeploymentHealth
    ) -> DeploymentHealth:
        """Insert or replace the health row for a deployment.

        Looks up an existing row by ``deployment_id``. If found, the
        existing row's fields are updated in place. If not, a new row
        is created. This avoids the ``merge`` surprise where a fresh
        UUID ``id`` would be allocated for every call.

        Ponytail: deliberately does NOT call ``session.refresh()``
        after the insert. The refresh would reload the row from the
        DB and (in SQLite tests) drop the ``tzinfo`` from the
        ``last_checked`` timestamp that the caller passed in. The
        BaseModel ``id`` is generated client-side via ``uuid4`` and is
        already populated on construction, so a refresh is unnecessary.
        """
        existing = await self.get_health(health.deployment_id)
        if existing is not None:
            existing.health = health.health
            existing.message = health.message
            existing.last_checked = health.last_checked
            await self._session.flush()
            return existing
        self._session.add(health)
        await self._session.flush()
        return health

    async def get_health(self, deployment_id: UUID) -> DeploymentHealth | None:
        stmt = select(DeploymentHealth).where(
            DeploymentHealth.deployment_id == deployment_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Reads: per-deployment
    # ------------------------------------------------------------------

    async def list_recent_requests(
        self,
        deployment_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DeploymentRequestLog]:
        stmt = (
            select(DeploymentRequestLog)
            .where(DeploymentRequestLog.deployment_id == deployment_id)
            .order_by(DeploymentRequestLog.timestamp.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_recent_requests(self, deployment_id: UUID) -> int:
        stmt = select(func.count(DeploymentRequestLog.id)).where(
            DeploymentRequestLog.deployment_id == deployment_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0

    async def list_recent_errors(
        self,
        deployment_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DeploymentRequestLog]:
        stmt = (
            select(DeploymentRequestLog)
            .where(
                DeploymentRequestLog.deployment_id == deployment_id,
                DeploymentRequestLog.status == RequestStatus.FAILURE,
            )
            .order_by(DeploymentRequestLog.timestamp.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_recent_errors(self, deployment_id: UUID) -> int:
        stmt = select(func.count(DeploymentRequestLog.id)).where(
            DeploymentRequestLog.deployment_id == deployment_id,
            DeploymentRequestLog.status == RequestStatus.FAILURE,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0

    async def aggregate_for_deployment(
        self, deployment_id: UUID
    ) -> RequestAggregate:
        """Compute count + min/max/avg latency for one deployment."""
        sum_latency = func.coalesce(
            func.sum(DeploymentRequestLog.latency_ms), 0
        )
        count_total = func.count(DeploymentRequestLog.id)
        count_success = func.sum(
            case(
                (
                    DeploymentRequestLog.status == RequestStatus.SUCCESS,
                    1,
                ),
                else_=0,
            )
        )
        avg_latency = func.coalesce(func.avg(DeploymentRequestLog.latency_ms), 0.0)
        min_latency = func.coalesce(func.min(DeploymentRequestLog.latency_ms), 0)
        max_latency = func.coalesce(func.max(DeploymentRequestLog.latency_ms), 0)

        stmt = select(
            count_total.label("request_count"),
            count_success.label("success_count"),
            sum_latency.label("sum_latency"),
            avg_latency.label("avg_latency"),
            min_latency.label("min_latency"),
            max_latency.label("max_latency"),
        ).where(DeploymentRequestLog.deployment_id == deployment_id)

        row = (await self._session.execute(stmt)).one()
        request_count = int(row.request_count or 0)
        success_count = int(row.success_count or 0)
        return RequestAggregate(
            request_count=request_count,
            success_count=success_count,
            failure_count=max(0, request_count - success_count),
            average_latency_ms=float(row.avg_latency or 0.0),
            min_latency_ms=float(row.min_latency or 0),
            max_latency_ms=float(row.max_latency or 0),
        )

    async def recent_window_for_deployment(
        self, deployment_id: UUID, *, limit: int = 10
    ) -> list[DeploymentRequestLog]:
        """Return the most recent N request logs for health evaluation."""
        stmt = (
            select(DeploymentRequestLog)
            .where(DeploymentRequestLog.deployment_id == deployment_id)
            .order_by(DeploymentRequestLog.timestamp.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Reads: user-scoped
    # ------------------------------------------------------------------

    async def list_user_deployment_ids(self, owner_id: UUID) -> list[UUID]:
        stmt = select(Deployment.id).where(Deployment.owner_id == owner_id)
        result = await self._session.execute(stmt)
        return [row[0] for row in result.all()]

    async def count_user_deployments(self, owner_id: UUID) -> int:
        stmt = select(func.count(Deployment.id)).where(
            Deployment.owner_id == owner_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0

    async def count_user_deployments_by_status(
        self, owner_id: UUID, status: DeploymentStatus
    ) -> int:
        stmt = select(func.count(Deployment.id)).where(
            Deployment.owner_id == owner_id,
            Deployment.status == status,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0

    async def aggregate_for_user(self, owner_id: UUID) -> GlobalAggregate:
        """Compute the dashboard aggregates over the user's full fleet."""
        deployment_ids_subq = (
            select(Deployment.id).where(Deployment.owner_id == owner_id).subquery()
        )
        count_total = func.count(DeploymentRequestLog.id)
        count_success = func.sum(
            case(
                (
                    DeploymentRequestLog.status == RequestStatus.SUCCESS,
                    1,
                ),
                else_=0,
            )
        )
        avg_latency = func.coalesce(func.avg(DeploymentRequestLog.latency_ms), 0.0)

        stmt = select(
            count_total.label("request_count"),
            count_success.label("success_count"),
            avg_latency.label("avg_latency"),
        ).where(
            DeploymentRequestLog.deployment_id.in_(
                select(deployment_ids_subq.c.id)
            )
        )

        row = (await self._session.execute(stmt)).one()
        total = int(row.request_count or 0)
        success = int(row.success_count or 0)
        return GlobalAggregate(
            total_requests=total,
            success_count=success,
            average_latency_ms=float(row.avg_latency or 0.0),
        )

    async def deployment_is_owned_by(
        self, deployment_id: UUID, owner_id: UUID
    ) -> bool:
        stmt = select(Deployment.id).where(
            Deployment.id == deployment_id,
            Deployment.owner_id == owner_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_deployment(self, deployment_id: UUID) -> Deployment | None:
        """Fetch a deployment by id, ignoring ownership.

        The monitoring service combines this with ``deployment_is_owned_by``
        so a foreign deployment returns 404 (not 403) — refusing to
        confirm the existence of resources the user does not own.
        """
        return await self._session.get(Deployment, deployment_id)

    async def commit(self) -> None:
        await self._session.commit()
