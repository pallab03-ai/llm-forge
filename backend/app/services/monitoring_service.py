"""Monitoring service: dashboard aggregates, health evaluation, request logging.

Owns the business rules for the monitoring surface:

- ``log_request`` persists a single inference call's metadata after the
  deployment service finishes a ``/generate`` call.
- ``get_dashboard`` returns a user-scoped summary that combines
  deployment counts and lifetime request aggregates.
- ``get_health`` evaluates the latest health verdict for a deployment
  and persists a snapshot in ``deployment_healths``.
- ``get_metrics``, ``list_requests``, ``list_errors`` are thin wrappers
  over the repository methods plus ownership enforcement.

No HTTP, no SQL. Pure business logic on top of the repository.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from app.models.deployment import Deployment, DeploymentStatus
from app.models.monitoring import (
    DeploymentHealth,
    DeploymentHealthState,
    DeploymentRequestLog,
    RequestStatus,
)
from app.repositories.monitoring_repository import MonitoringRepository
from app.schemas.monitoring import (
    DashboardResponse,
    DeploymentHealthResponse,
    DeploymentMetricsResponse,
    ErrorLogItem,
    ErrorLogListResponse,
    RequestLogItem,
    RequestLogListResponse,
)


# ---------------------------------------------------------------------------
# Tuning constants for the deterministic health rules
# ---------------------------------------------------------------------------

# How many recent requests inform the failure-rate check.
HEALTH_WINDOW_SIZE: int = 10
# >50% failures in the recent window marks the deployment DEGRADED.
HEALTH_FAILURE_RATE_THRESHOLD: float = 0.5
# >5s average latency in the recent window marks the deployment DEGRADED.
HEALTH_LATENCY_THRESHOLD_MS: float = 5_000.0
# Minimum requests before we apply the failure-rate or latency rule. With
# fewer requests, the verdict is HEALTHY (avoid noisy degradation when
# a single slow request happens to be the only one).
HEALTH_MIN_SAMPLES: int = 3


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class MonitoringError(Exception):
    code = "MONITORING_ERROR"
    http_status = 400


class MonitoringDeploymentNotFoundError(MonitoringError):
    code = "DEPLOYMENT_NOT_FOUND"
    http_status = 404

    def __init__(self, deployment_id: UUID) -> None:
        self.deployment_id = deployment_id
        super().__init__(f"Deployment not found: {deployment_id}")


class MonitoringDeploymentAccessDeniedError(MonitoringError):
    code = "DEPLOYMENT_ACCESS_DENIED"
    http_status = 403

    def __init__(self, deployment_id: UUID) -> None:
        self.deployment_id = deployment_id
        super().__init__(f"Access to deployment {deployment_id} is denied.")


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RequestLogInput:
    """The metadata we want to persist about one inference call.

    The deployment service fills this in after the ``/generate`` call
    finishes. ``prompt_length`` and ``response_length`` are character
    counts only — the prompt and response text are never sent to the
    monitoring layer.
    """

    deployment_id: UUID
    timestamp: datetime
    latency_ms: int
    status: RequestStatus
    prompt_length: int
    response_length: int | None
    error_type: str | None = None
    error_message: str | None = None
    error_status_code: int | None = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class MonitoringService:
    def __init__(self, repository: MonitoringRepository) -> None:
        self._repo = repository

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def log_request(self, entry: RequestLogInput) -> DeploymentRequestLog:
        """Persist a single request log row.

        Ponytail: this is the only write path. Aggregates are derived on
        demand from the log; we deliberately do not maintain a separate
        aggregate cache table.
        """
        record = DeploymentRequestLog(
            deployment_id=entry.deployment_id,
            timestamp=entry.timestamp,
            latency_ms=entry.latency_ms,
            status=entry.status,
            prompt_length=entry.prompt_length,
            response_length=entry.response_length,
            error_type=entry.error_type,
            error_message=entry.error_message,
            error_status_code=entry.error_status_code,
        )
        record = await self._repo.add_request_log(record)
        await self._repo.commit()
        return record

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    async def get_dashboard(self, *, user_id: UUID) -> DashboardResponse:
        deployment_count = await self._repo.count_user_deployments(user_id)
        active = await self._repo.count_user_deployments_by_status(
            user_id, DeploymentStatus.ACTIVE
        )
        failed = await self._repo.count_user_deployments_by_status(
            user_id, DeploymentStatus.FAILED
        )
        global_agg = await self._repo.aggregate_for_user(user_id)
        success_rate = (
            global_agg.success_count / global_agg.total_requests
            if global_agg.total_requests > 0
            else 0.0
        )
        return DashboardResponse(
            deployment_count=deployment_count,
            active_deployments=active,
            failed_deployments=failed,
            total_requests=global_agg.total_requests,
            success_rate=round(success_rate, 4),
            average_latency_ms=round(global_agg.average_latency_ms, 2),
        )

    # ------------------------------------------------------------------
    # Per-deployment
    # ------------------------------------------------------------------

    async def get_health(
        self,
        deployment_id: UUID,
        *,
        user_id: UUID,
    ) -> DeploymentHealthResponse:
        """Compute the current health verdict for a deployment.

        The verdict is recomputed on every call. The result is also
        upserted into ``deployment_healths`` so the per-deployment
        ``last_checked`` timestamp is stable across API calls.
        """
        deployment = await self._ensure_access(deployment_id, user_id)
        verdict, message = await self._evaluate_health(deployment)
        snapshot = DeploymentHealth(
            deployment_id=deployment.id,
            health=verdict,
            message=message,
            last_checked=datetime.now(timezone.utc),
        )
        await self._repo.upsert_health(snapshot)
        await self._repo.commit()

        return DeploymentHealthResponse(
            deployment_id=deployment.id,
            status=deployment.status.value,
            health=verdict,
            last_checked=snapshot.last_checked,
            message=message,
        )

    async def get_metrics(
        self,
        deployment_id: UUID,
        *,
        user_id: UUID,
    ) -> DeploymentMetricsResponse:
        await self._ensure_access(deployment_id, user_id)
        agg = await self._repo.aggregate_for_deployment(deployment_id)
        return DeploymentMetricsResponse(
            request_count=agg.request_count,
            success_count=agg.success_count,
            failure_count=agg.failure_count,
            average_latency_ms=round(agg.average_latency_ms, 2),
            min_latency_ms=agg.min_latency_ms,
            max_latency_ms=agg.max_latency_ms,
        )

    async def list_requests(
        self,
        deployment_id: UUID,
        *,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> RequestLogListResponse:
        await self._ensure_access(deployment_id, user_id)
        items = await self._repo.list_recent_requests(
            deployment_id, limit=limit, offset=offset
        )
        total = await self._repo.count_recent_requests(deployment_id)
        return RequestLogListResponse(
            items=[RequestLogItem.model_validate(i) for i in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def list_errors(
        self,
        deployment_id: UUID,
        *,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> ErrorLogListResponse:
        await self._ensure_access(deployment_id, user_id)
        items = await self._repo.list_recent_errors(
            deployment_id, limit=limit, offset=offset
        )
        total = await self._repo.count_recent_errors(deployment_id)
        error_items: list[ErrorLogItem] = []
        for row in items:
            # Defensive: filter out rows that are somehow marked failure
            # but lack error metadata. The schema enforces NOT NULL on
            # status, but the error_* columns are nullable for success
            # rows.
            if (
                row.error_type is None
                or row.error_message is None
                or row.error_status_code is None
            ):
                continue
            error_items.append(
                ErrorLogItem(
                    timestamp=row.timestamp,
                    error_type=row.error_type,
                    message=row.error_message,
                    status_code=row.error_status_code,
                )
            )
        return ErrorLogListResponse(
            items=error_items,
            total=total,
            limit=limit,
            offset=offset,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _ensure_access(
        self, deployment_id: UUID, user_id: UUID
    ) -> Deployment:
        # 404 for both "not found" and "exists but foreign" — never
        # confirm the existence of someone else's deployment.
        if not await self._repo.deployment_is_owned_by(deployment_id, user_id):
            raise MonitoringDeploymentNotFoundError(deployment_id)
        deployment = await self._repo.get_deployment(deployment_id)
        if deployment is None:
            raise MonitoringDeploymentNotFoundError(deployment_id)
        return deployment

    async def _evaluate_health(
        self, deployment: Deployment
    ) -> tuple[DeploymentHealthState, str]:
        # Rule 1: inactive deployments are UNAVAILABLE.
        if deployment.status != DeploymentStatus.ACTIVE:
            return (
                DeploymentHealthState.UNAVAILABLE,
                f"Deployment is {deployment.status.value}; not serving requests.",
            )

        recent = await self._repo.recent_window_for_deployment(
            deployment.id, limit=HEALTH_WINDOW_SIZE
        )

        # Rule 2: with too few samples, the verdict stays HEALTHY.
        if len(recent) < HEALTH_MIN_SAMPLES:
            return (
                DeploymentHealthState.HEALTHY,
                "All systems normal.",
            )

        failure_count = sum(1 for r in recent if r.status == RequestStatus.FAILURE)
        failure_rate = failure_count / len(recent)
        avg_latency = sum(r.latency_ms for r in recent) / len(recent)

        if failure_rate > HEALTH_FAILURE_RATE_THRESHOLD:
            return (
                DeploymentHealthState.DEGRADED,
                f"High failure rate ({int(failure_rate * 100)}% of last {len(recent)} requests).",
            )
        if avg_latency > HEALTH_LATENCY_THRESHOLD_MS:
            return (
                DeploymentHealthState.DEGRADED,
                f"Elevated latency ({int(avg_latency)}ms average over last {len(recent)} requests).",
            )
        return (
            DeploymentHealthState.HEALTHY,
            "All systems normal.",
        )


__all__ = [
    "HEALTH_WINDOW_SIZE",
    "HEALTH_FAILURE_RATE_THRESHOLD",
    "HEALTH_LATENCY_THRESHOLD_MS",
    "HEALTH_MIN_SAMPLES",
    "MonitoringError",
    "MonitoringDeploymentNotFoundError",
    "MonitoringDeploymentAccessDeniedError",
    "MonitoringService",
    "RequestLogInput",
]
