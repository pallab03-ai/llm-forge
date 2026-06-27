"""Tests for the Monitoring Service.

Covers:
- Repository: aggregate queries, error/request listing, ownership check
- Service: dashboard aggregates, health evaluation, request logging,
  ownership enforcement
- API: 5 endpoints, authentication, pagination
- Integration: DeploymentService.generate logs request metadata to the
  monitoring tables (success + failure paths)
"""

from __future__ import annotations

import tempfile
import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deployments import _get_deployment_service
from app.core.security import hash_password
from app.main import app
from app.models.dataset import (
    Dataset,
    DatasetFormat,
    DatasetStatus,
    DatasetType,
    DatasetVersion,
)
from app.models.deployment import Deployment, DeploymentStatus
from app.models.evaluation import Evaluation, EvaluationStatus
from app.models.model import Model, ModelVersion, ModelVersionStatus
from app.models.monitoring import (
    DeploymentHealth,
    DeploymentHealthState,
    DeploymentRequestLog,
    RequestStatus,
)
from app.models.training_job import TrainingJob, TrainingJobStatus, TrainingType
from app.models.user import User
from app.repositories.deployment_repository import DeploymentRepository
from app.repositories.evaluation_repository import EvaluationRepository
from app.repositories.model_repository import ModelRepository
from app.repositories.monitoring_repository import MonitoringRepository
from app.repositories.training_job_repository import TrainingJobRepository
from app.schemas.deployment import DeploymentCreateRequest, GenerateRequest
from app.services.deployment_service import DeploymentService
from app.services.inference_service import InferenceError
from app.services.monitoring_service import (
    HEALTH_FAILURE_RATE_THRESHOLD,
    HEALTH_LATENCY_THRESHOLD_MS,
    HEALTH_MIN_SAMPLES,
    HEALTH_WINDOW_SIZE,
    MonitoringDeploymentNotFoundError,
    MonitoringService,
    RequestLogInput,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeInferenceService:
    """Test double for InferenceService."""

    def __init__(self, response: str = "mock response") -> None:
        self.response = response
        self.load_side_effect: Exception | None = None
        self.generate_side_effect: Exception | None = None

    def load(self, artifact_path: str, base_model: str) -> None:  # noqa: ARG002
        if self.load_side_effect is not None:
            raise self.load_side_effect

    def generate(self, prompt: str, **kwargs) -> str:  # noqa: ARG002
        if self.generate_side_effect is not None:
            raise self.generate_side_effect
        return self.response

    def unload(self) -> None:
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_user(
    db_session: AsyncSession,
    *,
    email: str = "monitor@example.com",
) -> uuid.UUID:
    user = User(
        email=email,
        username=email.split("@")[0],
        role="user",
    )
    user.password_hash = hash_password("StrongPass123!")
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()
    return user.id


async def _seed_dataset(
    db_session: AsyncSession, user_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    ds = Dataset(
        name=f"ds-{user_id}",
        dataset_type=DatasetType.INSTRUCTION_TUNING,
        format=DatasetFormat.CSV,
        status=DatasetStatus.READY,
        created_by=user_id,
    )
    db_session.add(ds)
    await db_session.flush()

    fd, path = tempfile.mkstemp(suffix=".csv")
    import os as _os

    with _os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("instruction,response\nWhat is 2+2?,4\n")

    ver = DatasetVersion(
        dataset_id=ds.id,
        version_number=1,
        file_path=path,
        file_size_bytes=60,
        record_count=2,
    )
    db_session.add(ver)
    await db_session.flush()
    await db_session.commit()
    return ds.id, ver.id


async def _seed_completed_job(
    db_session: AsyncSession,
    user_id: uuid.UUID,
    dataset_id: uuid.UUID,
    dataset_version_id: uuid.UUID,
    artifact_path: str,
) -> uuid.UUID:
    job = TrainingJob(
        user_id=user_id,
        dataset_id=dataset_id,
        dataset_version_id=dataset_version_id,
        base_model="google/gemma-3-1b-it",
        training_type=TrainingType.QLORA,
        configuration={
            "epochs": 1,
            "batch_size": 2,
            "learning_rate": 2e-4,
            "max_seq_length": 512,
        },
        status=TrainingJobStatus.COMPLETED,
        artifact_path=artifact_path,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    repo = TrainingJobRepository(db_session)
    await repo.create(job)
    await repo.commit()
    return job.id


async def _seed_completed_evaluation(
    db_session: AsyncSession,
    user_id: uuid.UUID,
    dataset_id: uuid.UUID,
    dataset_version_id: uuid.UUID,
    model_id: uuid.UUID,
) -> uuid.UUID:
    ev = Evaluation(
        user_id=user_id,
        dataset_id=dataset_id,
        dataset_version_id=dataset_version_id,
        model_id=model_id,
        status=EvaluationStatus.COMPLETED,
        rouge_score=0.23,
        bertscore_precision=0.81,
        bertscore_recall=0.87,
        bertscore_f1=0.84,
        semantic_similarity=0.77,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    repo = EvaluationRepository(db_session)
    await repo.create(ev)
    await repo.commit()
    return ev.id


async def _seed_model_version(
    db_session: AsyncSession,
    user_id: uuid.UUID,
    artifact_path: str = "/tmp/adapter",
    status: ModelVersionStatus = ModelVersionStatus.STAGING,
) -> tuple[uuid.UUID, uuid.UUID]:
    ds_id, dver_id = await _seed_dataset(db_session, user_id)
    job_id = await _seed_completed_job(
        db_session, user_id, ds_id, dver_id, artifact_path
    )
    eval_id = await _seed_completed_evaluation(
        db_session, user_id, ds_id, dver_id, job_id
    )

    model = Model(owner_id=user_id, name="Test Model", description=None)
    model_repo = ModelRepository(db_session)
    await model_repo.create_model(model)
    await model_repo.commit()

    version = ModelVersion(
        model_id=model.id,
        training_job_id=job_id,
        evaluation_id=eval_id,
        version_number=1,
        artifact_path=artifact_path,
        metrics_snapshot={},
        status=status,
    )
    version = await model_repo.create_version(version)
    await model_repo.commit()
    return model.id, version.id


async def _seed_deployment(
    db_session: AsyncSession,
    user_id: uuid.UUID,
    version_id: uuid.UUID,
    *,
    status: DeploymentStatus = DeploymentStatus.ACTIVE,
) -> uuid.UUID:
    deployment = Deployment(
        owner_id=user_id,
        model_version_id=version_id,
        deployment_name="mon-bot",
        endpoint_name="mon-bot-v1",
        status=status,
    )
    repo = DeploymentRepository(db_session)
    deployment = await repo.create_deployment(deployment)
    await repo.commit()
    return deployment.id


async def _seed_request_log(
    db_session: AsyncSession,
    deployment_id: uuid.UUID,
    *,
    status: RequestStatus,
    latency_ms: int = 100,
    error_type: str | None = None,
    error_message: str | None = None,
    error_status_code: int | None = None,
    response_length: int | None = 10,
) -> None:
    repo = MonitoringRepository(db_session)
    await repo.add_request_log(
        DeploymentRequestLog(
            deployment_id=deployment_id,
            timestamp=datetime.now(timezone.utc),
            latency_ms=latency_ms,
            status=status,
            prompt_length=20,
            response_length=response_length,
            error_type=error_type,
            error_message=error_message,
            error_status_code=error_status_code,
        )
    )
    await repo.commit()


async def _register_and_login(
    client: AsyncClient,
    email: str = "monitor@example.com",
    username: str = "monitor",
) -> dict:
    payload = {
        "email": email,
        "username": username,
        "password": "StrongPass123!",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict:
    return await _register_and_login(client)


@pytest.fixture
async def other_user_headers(client: AsyncClient) -> dict:
    return await _register_and_login(
        client, email="other@example.com", username="other"
    )


# ---------------------------------------------------------------------------
# Repository tests
# ---------------------------------------------------------------------------


class TestMonitoringRepository:
    async def test_aggregate_for_deployment_empty(self, db_session: AsyncSession):
        user_id = await _seed_user(db_session)
        _, version_id = await _seed_model_version(db_session, user_id)
        deployment_id = await _seed_deployment(db_session, user_id, version_id)

        repo = MonitoringRepository(db_session)
        agg = await repo.aggregate_for_deployment(deployment_id)
        assert agg.request_count == 0
        assert agg.success_count == 0
        assert agg.failure_count == 0
        assert agg.average_latency_ms == 0.0
        assert agg.min_latency_ms == 0
        assert agg.max_latency_ms == 0

    async def test_aggregate_for_deployment_with_mixed_requests(
        self, db_session: AsyncSession
    ):
        user_id = await _seed_user(db_session)
        _, version_id = await _seed_model_version(db_session, user_id)
        deployment_id = await _seed_deployment(db_session, user_id, version_id)

        for ms in (100, 200, 300, 400, 500):
            await _seed_request_log(
                db_session,
                deployment_id,
                status=RequestStatus.SUCCESS,
                latency_ms=ms,
                response_length=ms,
            )
        for ms in (200, 800):
            await _seed_request_log(
                db_session,
                deployment_id,
                status=RequestStatus.FAILURE,
                latency_ms=ms,
                error_type="INFERENCE_ERROR",
                error_message="boom",
                error_status_code=500,
                response_length=None,
            )

        repo = MonitoringRepository(db_session)
        agg = await repo.aggregate_for_deployment(deployment_id)
        assert agg.request_count == 7
        assert agg.success_count == 5
        assert agg.failure_count == 2
        assert agg.average_latency_ms == pytest.approx(357.14, rel=0.01)
        assert agg.min_latency_ms == 100
        assert agg.max_latency_ms == 800

    async def test_list_recent_requests_orders_newest_first(
        self, db_session: AsyncSession
    ):
        user_id = await _seed_user(db_session)
        _, version_id = await _seed_model_version(db_session, user_id)
        deployment_id = await _seed_deployment(db_session, user_id, version_id)

        for i in range(3):
            await _seed_request_log(
                db_session,
                deployment_id,
                status=RequestStatus.SUCCESS,
                latency_ms=100 + i,
            )

        repo = MonitoringRepository(db_session)
        items = await repo.list_recent_requests(deployment_id, limit=10, offset=0)
        assert len(items) == 3
        # The last-inserted row has the highest timestamp; it must be first.
        assert items[0].latency_ms == 102
        assert items[-1].latency_ms == 100

    async def test_list_recent_errors_filters_failures_only(
        self, db_session: AsyncSession
    ):
        user_id = await _seed_user(db_session)
        _, version_id = await _seed_model_version(db_session, user_id)
        deployment_id = await _seed_deployment(db_session, user_id, version_id)

        await _seed_request_log(
            db_session, deployment_id, status=RequestStatus.SUCCESS
        )
        await _seed_request_log(
            db_session,
            deployment_id,
            status=RequestStatus.FAILURE,
            error_type="INFERENCE_ERROR",
            error_message="boom",
            error_status_code=500,
            response_length=None,
        )

        repo = MonitoringRepository(db_session)
        items = await repo.list_recent_errors(deployment_id, limit=10, offset=0)
        assert len(items) == 1
        assert items[0].error_type == "INFERENCE_ERROR"

    async def test_user_aggregates_skip_foreign_deployments(
        self, db_session: AsyncSession
    ):
        user_a = await _seed_user(db_session, email="a@x.com")
        user_b = await _seed_user(db_session, email="b@x.com")

        _, va = await _seed_model_version(db_session, user_a)
        _, vb = await _seed_model_version(db_session, user_b)

        dep_a = await _seed_deployment(db_session, user_a, va)
        dep_b = await _seed_deployment(db_session, user_b, vb)

        await _seed_request_log(db_session, dep_a, status=RequestStatus.SUCCESS, latency_ms=100)
        await _seed_request_log(db_session, dep_b, status=RequestStatus.SUCCESS, latency_ms=999)

        repo = MonitoringRepository(db_session)
        agg = await repo.aggregate_for_user(user_a)
        # Only the user's own row counts.
        assert agg.total_requests == 1
        assert agg.average_latency_ms == 100.0


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------


class TestMonitoringService:
    async def test_dashboard_aggregates(self, db_session: AsyncSession):
        user_id = await _seed_user(db_session)
        _, va = await _seed_model_version(db_session, user_id)
        _, vb = await _seed_model_version(db_session, user_id)

        active = await _seed_deployment(
            db_session, user_id, va, status=DeploymentStatus.ACTIVE
        )
        await _seed_deployment(
            db_session, user_id, vb, status=DeploymentStatus.FAILED
        )

        await _seed_request_log(
            db_session, active, status=RequestStatus.SUCCESS, latency_ms=200
        )
        await _seed_request_log(
            db_session,
            active,
            status=RequestStatus.FAILURE,
            latency_ms=600,
            error_type="X",
            error_message="err",
            error_status_code=500,
            response_length=None,
        )

        repo = MonitoringRepository(db_session)
        service = MonitoringService(repo)
        result = await service.get_dashboard(user_id=user_id)

        assert result.deployment_count == 2
        assert result.active_deployments == 1
        assert result.failed_deployments == 1
        assert result.total_requests == 2
        assert result.success_rate == 0.5
        assert result.average_latency_ms == 400.0

    async def test_dashboard_empty_user_returns_zeros(
        self, db_session: AsyncSession
    ):
        user_id = await _seed_user(db_session)
        service = MonitoringService(MonitoringRepository(db_session))
        result = await service.get_dashboard(user_id=user_id)
        assert result.deployment_count == 0
        assert result.total_requests == 0
        assert result.success_rate == 0.0
        assert result.average_latency_ms == 0.0

    async def test_health_inactive_deployment_is_unavailable(
        self, db_session: AsyncSession
    ):
        user_id = await _seed_user(db_session)
        _, version_id = await _seed_model_version(db_session, user_id)
        dep_id = await _seed_deployment(
            db_session, user_id, version_id, status=DeploymentStatus.FAILED
        )

        service = MonitoringService(MonitoringRepository(db_session))
        result = await service.get_health(dep_id, user_id=user_id)
        assert result.health == DeploymentHealthState.UNAVAILABLE
        assert result.status == "failed"

    async def test_health_active_with_no_requests_is_healthy(
        self, db_session: AsyncSession
    ):
        user_id = await _seed_user(db_session)
        _, version_id = await _seed_model_version(db_session, user_id)
        dep_id = await _seed_deployment(
            db_session, user_id, version_id, status=DeploymentStatus.ACTIVE
        )

        service = MonitoringService(MonitoringRepository(db_session))
        result = await service.get_health(dep_id, user_id=user_id)
        assert result.health == DeploymentHealthState.HEALTHY
        assert "normal" in result.message.lower()

    async def test_health_high_failure_rate_marks_degraded(
        self, db_session: AsyncSession
    ):
        user_id = await _seed_user(db_session)
        _, version_id = await _seed_model_version(db_session, user_id)
        dep_id = await _seed_deployment(
            db_session, user_id, version_id, status=DeploymentStatus.ACTIVE
        )
        # HEALTH_MIN_SAMPLES + 1 entries; 60% failures.
        for i in range(HEALTH_MIN_SAMPLES):
            await _seed_request_log(
                db_session,
                dep_id,
                status=RequestStatus.FAILURE,
                latency_ms=100,
                error_type="X",
                error_message="err",
                error_status_code=500,
                response_length=None,
            )
        # 1 success out of 5 → 80% failure > threshold.
        await _seed_request_log(
            db_session, dep_id, status=RequestStatus.SUCCESS, latency_ms=100
        )

        service = MonitoringService(MonitoringRepository(db_session))
        result = await service.get_health(dep_id, user_id=user_id)
        assert result.health == DeploymentHealthState.DEGRADED
        assert "failure" in result.message.lower()

    async def test_health_elevated_latency_marks_degraded(
        self, db_session: AsyncSession
    ):
        user_id = await _seed_user(db_session)
        _, version_id = await _seed_model_version(db_session, user_id)
        dep_id = await _seed_deployment(
            db_session, user_id, version_id, status=DeploymentStatus.ACTIVE
        )
        # All successes but each one slow.
        for _ in range(HEALTH_MIN_SAMPLES + 1):
            await _seed_request_log(
                db_session,
                dep_id,
                status=RequestStatus.SUCCESS,
                latency_ms=int(HEALTH_LATENCY_THRESHOLD_MS + 1000),
            )

        service = MonitoringService(MonitoringRepository(db_session))
        result = await service.get_health(dep_id, user_id=user_id)
        assert result.health == DeploymentHealthState.DEGRADED
        assert "latency" in result.message.lower()

    async def test_health_upserts_snapshot_with_timestamp(
        self, db_session: AsyncSession
    ):
        user_id = await _seed_user(db_session)
        _, version_id = await _seed_model_version(db_session, user_id)
        dep_id = await _seed_deployment(
            db_session, user_id, version_id, status=DeploymentStatus.ACTIVE
        )

        service = MonitoringService(MonitoringRepository(db_session))
        result = await service.get_health(dep_id, user_id=user_id)
        assert result.last_checked.tzinfo is not None

        # DeploymentHealth has both an `id` PK (from BaseModel) and a
        # UNIQUE deployment_id, so look it up by deployment_id.
        from sqlalchemy import select as _select

        snapshot = (
            await db_session.execute(
                _select(DeploymentHealth).where(
                    DeploymentHealth.deployment_id == dep_id
                )
            )
        ).scalar_one_or_none()
        assert snapshot is not None
        assert snapshot.health == DeploymentHealthState.HEALTHY

    async def test_health_recent_window_only_uses_last_n(
        self, db_session: AsyncSession
    ):
        user_id = await _seed_user(db_session)
        _, version_id = await _seed_model_version(db_session, user_id)
        dep_id = await _seed_deployment(
            db_session, user_id, version_id, status=DeploymentStatus.ACTIVE
        )
        # Insert HEALTH_WINDOW_SIZE failures, then HEALTH_WINDOW_SIZE
        # successes. The recent window pulls only the last
        # HEALTH_WINDOW_SIZE rows (the successes), so the failure rate
        # in the window is 0% and the verdict must be HEALTHY.
        for _ in range(HEALTH_WINDOW_SIZE):
            await _seed_request_log(
                db_session,
                dep_id,
                status=RequestStatus.FAILURE,
                latency_ms=50,
                error_type="X",
                error_message="err",
                error_status_code=500,
                response_length=None,
            )
        for _ in range(HEALTH_WINDOW_SIZE):
            await _seed_request_log(
                db_session, dep_id, status=RequestStatus.SUCCESS, latency_ms=50
            )

        service = MonitoringService(MonitoringRepository(db_session))
        result = await service.get_health(dep_id, user_id=user_id)
        assert result.health == DeploymentHealthState.HEALTHY

    async def test_metrics_endpoint_shape(self, db_session: AsyncSession):
        user_id = await _seed_user(db_session)
        _, version_id = await _seed_model_version(db_session, user_id)
        dep_id = await _seed_deployment(
            db_session, user_id, version_id, status=DeploymentStatus.ACTIVE
        )

        await _seed_request_log(
            db_session, dep_id, status=RequestStatus.SUCCESS, latency_ms=100
        )
        await _seed_request_log(
            db_session,
            dep_id,
            status=RequestStatus.FAILURE,
            latency_ms=400,
            error_type="X",
            error_message="err",
            error_status_code=500,
            response_length=None,
        )

        service = MonitoringService(MonitoringRepository(db_session))
        result = await service.get_metrics(dep_id, user_id=user_id)
        assert result.request_count == 2
        assert result.success_count == 1
        assert result.failure_count == 1
        assert result.average_latency_ms == 250.0
        assert result.min_latency_ms == 100
        assert result.max_latency_ms == 400

    async def test_request_log_lists_with_pagination(
        self, db_session: AsyncSession
    ):
        user_id = await _seed_user(db_session)
        _, version_id = await _seed_model_version(db_session, user_id)
        dep_id = await _seed_deployment(
            db_session, user_id, version_id, status=DeploymentStatus.ACTIVE
        )
        for _ in range(5):
            await _seed_request_log(
                db_session, dep_id, status=RequestStatus.SUCCESS, latency_ms=50
            )

        service = MonitoringService(MonitoringRepository(db_session))
        result = await service.list_requests(
            dep_id, user_id=user_id, limit=2, offset=1
        )
        assert result.total == 5
        assert len(result.items) == 2
        assert result.limit == 2
        assert result.offset == 1

    async def test_error_log_filters_failures_with_metadata(
        self, db_session: AsyncSession
    ):
        user_id = await _seed_user(db_session)
        _, version_id = await _seed_model_version(db_session, user_id)
        dep_id = await _seed_deployment(
            db_session, user_id, version_id, status=DeploymentStatus.ACTIVE
        )
        # A success row (should be filtered out).
        await _seed_request_log(
            db_session, dep_id, status=RequestStatus.SUCCESS, latency_ms=50
        )
        # A failure row (should be returned).
        await _seed_request_log(
            db_session,
            dep_id,
            status=RequestStatus.FAILURE,
            latency_ms=300,
            error_type="INFERENCE_ERROR",
            error_message="boom",
            error_status_code=500,
            response_length=None,
        )

        service = MonitoringService(MonitoringRepository(db_session))
        result = await service.list_errors(dep_id, user_id=user_id)
        assert result.total == 1
        assert len(result.items) == 1
        assert result.items[0].error_type == "INFERENCE_ERROR"
        assert result.items[0].status_code == 500

    async def test_access_denied_for_foreign_deployment(
        self, db_session: AsyncSession
    ):
        user_a = await _seed_user(db_session, email="alpha@x.com")
        user_b = await _seed_user(db_session, email="beta@x.com")
        _, version_id = await _seed_model_version(db_session, user_a)
        dep_id = await _seed_deployment(db_session, user_a, version_id)

        service = MonitoringService(MonitoringRepository(db_session))
        with pytest.raises(MonitoringDeploymentNotFoundError):
            await service.get_health(dep_id, user_id=user_b)
        with pytest.raises(MonitoringDeploymentNotFoundError):
            await service.get_metrics(dep_id, user_id=user_b)

    async def test_log_request_persists_row(self, db_session: AsyncSession):
        user_id = await _seed_user(db_session)
        _, version_id = await _seed_model_version(db_session, user_id)
        dep_id = await _seed_deployment(db_session, user_id, version_id)

        service = MonitoringService(MonitoringRepository(db_session))
        await service.log_request(
            RequestLogInput(
                deployment_id=dep_id,
                timestamp=datetime.now(timezone.utc),
                latency_ms=250,
                status=RequestStatus.SUCCESS,
                prompt_length=42,
                response_length=128,
            )
        )

        repo = MonitoringRepository(db_session)
        items = await repo.list_recent_requests(dep_id, limit=10, offset=0)
        assert len(items) == 1
        assert items[0].latency_ms == 250
        assert items[0].response_length == 128


# ---------------------------------------------------------------------------
# Deployment service → monitoring integration
# ---------------------------------------------------------------------------


class TestDeploymentServiceLogsRequests:
    """The deployment service should log every /generate call to monitoring."""

    async def test_generate_success_writes_a_log_row(
        self, db_session: AsyncSession
    ):
        user_id = await _seed_user(db_session)
        artifact_dir = tempfile.mkdtemp()
        _, version_id = await _seed_model_version(
            db_session, user_id, artifact_path=artifact_dir
        )
        dep_id = await _seed_deployment(
            db_session, user_id, version_id, status=DeploymentStatus.ACTIVE
        )

        fake_inference = FakeInferenceService(response="hello world")
        monitoring_service = MonitoringService(MonitoringRepository(db_session))
        service = DeploymentService(
            deployment_repo=DeploymentRepository(db_session),
            model_repo=ModelRepository(db_session),
            training_job_repo=TrainingJobRepository(db_session),
            inference_service=fake_inference,
            monitoring_service=monitoring_service,
        )

        result = await service.generate(
            dep_id,
            user_id=user_id,
            request=GenerateRequest.model_construct(prompt="hi there"),
        )
        assert result.response == "hello world"

        # The log row should exist with the right metadata.
        repo = MonitoringRepository(db_session)
        items = await repo.list_recent_requests(dep_id, limit=10, offset=0)
        assert len(items) == 1
        assert items[0].status == RequestStatus.SUCCESS
        assert items[0].prompt_length == len("hi there")
        assert items[0].response_length == len("hello world")
        assert items[0].error_type is None

    async def test_generate_failure_writes_a_failure_log_row(
        self, db_session: AsyncSession
    ):
        user_id = await _seed_user(db_session)
        artifact_dir = tempfile.mkdtemp()
        _, version_id = await _seed_model_version(
            db_session, user_id, artifact_path=artifact_dir
        )
        dep_id = await _seed_deployment(
            db_session, user_id, version_id, status=DeploymentStatus.ACTIVE
        )

        fake_inference = FakeInferenceService()
        fake_inference.generate_side_effect = InferenceError("oom")
        monitoring_service = MonitoringService(MonitoringRepository(db_session))
        service = DeploymentService(
            deployment_repo=DeploymentRepository(db_session),
            model_repo=ModelRepository(db_session),
            training_job_repo=TrainingJobRepository(db_session),
            inference_service=fake_inference,
            monitoring_service=monitoring_service,
        )

        with pytest.raises(Exception):
            await service.generate(
                dep_id,
                user_id=user_id,
                request=GenerateRequest.model_construct(prompt="x"),
            )

        repo = MonitoringRepository(db_session)
        items = await repo.list_recent_errors(dep_id, limit=10, offset=0)
        assert len(items) == 1
        assert items[0].error_type == "INFERENCE_ERROR"
        assert items[0].error_status_code == 400
        assert "oom" in (items[0].error_message or "")

    async def test_generate_without_monitoring_service_works(
        self, db_session: AsyncSession
    ):
        # Backward-compat: existing callers that pass no monitoring
        # service must continue to work and must not write log rows.
        user_id = await _seed_user(db_session)
        artifact_dir = tempfile.mkdtemp()
        _, version_id = await _seed_model_version(
            db_session, user_id, artifact_path=artifact_dir
        )
        dep_id = await _seed_deployment(
            db_session, user_id, version_id, status=DeploymentStatus.ACTIVE
        )

        service = DeploymentService(
            deployment_repo=DeploymentRepository(db_session),
            model_repo=ModelRepository(db_session),
            training_job_repo=TrainingJobRepository(db_session),
            inference_service=FakeInferenceService(),
            monitoring_service=None,
        )
        result = await service.generate(
            dep_id,
            user_id=user_id,
            request=GenerateRequest.model_construct(prompt="hi"),
        )
        assert result.response == "mock response"

        repo = MonitoringRepository(db_session)
        items = await repo.list_recent_requests(dep_id, limit=10, offset=0)
        assert items == []


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


@pytest.fixture
async def override_deployment_service_with_monitoring():
    """Wire the deployment service with a monitoring service so that
    integration test traffic logs to the same DB."""
    from fastapi import Depends
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.session import get_db

    fake_inference = FakeInferenceService()
    monitoring_service_holder: dict = {}

    def _make_service(db: AsyncSession = Depends(get_db)) -> DeploymentService:
        monitoring = MonitoringService(MonitoringRepository(db))
        monitoring_service_holder["svc"] = monitoring
        return DeploymentService(
            deployment_repo=DeploymentRepository(db),
            model_repo=ModelRepository(db),
            training_job_repo=TrainingJobRepository(db),
            inference_service=fake_inference,
            monitoring_service=monitoring,
        )

    app.dependency_overrides[_get_deployment_service] = _make_service
    yield fake_inference, monitoring_service_holder
    app.dependency_overrides.pop(_get_deployment_service, None)


class TestMonitoringAPI:
    async def test_dashboard_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/monitoring/dashboard")
        assert resp.status_code == 401

    async def test_dashboard_returns_empty_zeros(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.get(
            "/api/v1/monitoring/dashboard", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["deployment_count"] == 0
        assert data["active_deployments"] == 0
        assert data["total_requests"] == 0
        assert data["success_rate"] == 0.0

    async def test_dashboard_aggregates_real_data(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
    ):
        result = await db_session.execute(
            select(User).where(User.email == "monitor@example.com")
        )
        user_id = result.scalar_one().id
        _, va = await _seed_model_version(db_session, user_id)
        dep_id = await _seed_deployment(
            db_session, user_id, va, status=DeploymentStatus.ACTIVE
        )
        await _seed_request_log(
            db_session, dep_id, status=RequestStatus.SUCCESS, latency_ms=100
        )

        resp = await client.get(
            "/api/v1/monitoring/dashboard", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["deployment_count"] == 1
        assert data["active_deployments"] == 1
        assert data["total_requests"] == 1
        assert data["success_rate"] == 1.0

    async def test_health_endpoint(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
    ):
        result = await db_session.execute(
            select(User).where(User.email == "monitor@example.com")
        )
        user_id = result.scalar_one().id
        _, version_id = await _seed_model_version(db_session, user_id)
        dep_id = await _seed_deployment(
            db_session, user_id, version_id, status=DeploymentStatus.ACTIVE
        )

        resp = await client.get(
            f"/api/v1/deployments/{dep_id}/health", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["deployment_id"] == str(dep_id)
        assert data["status"] == "active"
        assert data["health"] == "healthy"
        assert "last_checked" in data

    async def test_health_404_for_foreign_deployment(
        self,
        client: AsyncClient,
        other_user_headers: dict,
        db_session: AsyncSession,
    ):
        user_id = await _seed_user(db_session, email="host@x.com")
        _, version_id = await _seed_model_version(db_session, user_id)
        dep_id = await _seed_deployment(db_session, user_id, version_id)

        resp = await client.get(
            f"/api/v1/deployments/{dep_id}/health", headers=other_user_headers
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "DEPLOYMENT_NOT_FOUND"

    async def test_metrics_endpoint(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
    ):
        result = await db_session.execute(
            select(User).where(User.email == "monitor@example.com")
        )
        user_id = result.scalar_one().id
        _, version_id = await _seed_model_version(db_session, user_id)
        dep_id = await _seed_deployment(db_session, user_id, version_id)

        await _seed_request_log(
            db_session, dep_id, status=RequestStatus.SUCCESS, latency_ms=100
        )
        await _seed_request_log(
            db_session,
            dep_id,
            status=RequestStatus.FAILURE,
            latency_ms=500,
            error_type="X",
            error_message="err",
            error_status_code=500,
            response_length=None,
        )

        resp = await client.get(
            f"/api/v1/deployments/{dep_id}/metrics", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["request_count"] == 2
        assert data["success_count"] == 1
        assert data["failure_count"] == 1
        assert data["min_latency_ms"] == 100
        assert data["max_latency_ms"] == 500

    async def test_requests_endpoint_pagination(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
    ):
        result = await db_session.execute(
            select(User).where(User.email == "monitor@example.com")
        )
        user_id = result.scalar_one().id
        _, version_id = await _seed_model_version(db_session, user_id)
        dep_id = await _seed_deployment(db_session, user_id, version_id)

        for _ in range(5):
            await _seed_request_log(
                db_session, dep_id, status=RequestStatus.SUCCESS, latency_ms=10
            )

        resp = await client.get(
            f"/api/v1/deployments/{dep_id}/requests",
            params={"limit": 2, "offset": 1},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["total"] == 5
        assert len(data["items"]) == 2

    async def test_errors_endpoint(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
    ):
        result = await db_session.execute(
            select(User).where(User.email == "monitor@example.com")
        )
        user_id = result.scalar_one().id
        _, version_id = await _seed_model_version(db_session, user_id)
        dep_id = await _seed_deployment(db_session, user_id, version_id)

        await _seed_request_log(
            db_session,
            dep_id,
            status=RequestStatus.FAILURE,
            error_type="INFERENCE_ERROR",
            error_message="boom",
            error_status_code=500,
            response_length=None,
        )

        resp = await client.get(
            f"/api/v1/deployments/{dep_id}/errors", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["error_type"] == "INFERENCE_ERROR"
        assert data["items"][0]["status_code"] == 500

    async def test_generate_endpoint_logs_to_monitoring(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        override_deployment_service_with_monitoring,
    ):
        result = await db_session.execute(
            select(User).where(User.email == "monitor@example.com")
        )
        user_id = result.scalar_one().id
        artifact_dir = tempfile.mkdtemp()
        _, version_id = await _seed_model_version(
            db_session, user_id, artifact_path=artifact_dir
        )
        create_resp = await client.post(
            "/api/v1/deployments",
            json={
                "model_version_id": str(version_id),
                "deployment_name": "log-bot",
                "endpoint_name": "log-bot-v1",
            },
            headers=auth_headers,
        )
        deployment_id = create_resp.json()["data"]["id"]
        await client.post(
            f"/api/v1/deployments/{deployment_id}/activate",
            headers=auth_headers,
        )

        await client.post(
            f"/api/v1/deployments/{deployment_id}/generate",
            json={"prompt": "hello"},
            headers=auth_headers,
        )

        resp = await client.get(
            f"/api/v1/deployments/{deployment_id}/requests",
            headers=auth_headers,
        )
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["status"] == "success"
        assert data["items"][0]["prompt_length"] == 5
        assert data["items"][0]["response_length"] == len("mock response")
