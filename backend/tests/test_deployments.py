"""Tests for the Deployment Service.

Covers:
- Deployment repository operations
- DeploymentService business rules (lifecycle, ownership, validation)
- API endpoints (POST/GET deployment, POST activate, POST generate)
- InferenceService caching and adapter loading seam
- Invalid transitions and access control

All real model loading is mocked. A separate test exercises the
InferenceService load/generate interface with a stub.
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
from app.models.training_job import TrainingJob, TrainingJobStatus, TrainingType
from app.models.user import User
from app.repositories.deployment_repository import DeploymentRepository
from app.repositories.evaluation_repository import EvaluationRepository
from app.repositories.model_repository import ModelRepository
from app.repositories.training_job_repository import TrainingJobRepository
from app.schemas.deployment import DeploymentCreateRequest, GenerateRequest
from app.services.deployment_service import (
    DeploymentAccessDeniedError,
    DeploymentAdapterNotFoundError,
    DeploymentAlreadyActiveError,
    DeploymentError,
    DeploymentInvalidStatusError,
    DeploymentModelVersionArchivedError,
    DeploymentModelVersionNotFoundError,
    DeploymentNotActiveError,
    DeploymentNotFoundError,
    DeploymentService,
)
from app.services.inference_service import InferenceError, InferenceService
from app.core.security import hash_password


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeInferenceService:
    """Test double for InferenceService."""

    def __init__(self, response: str = "mock response") -> None:
        self.response = response
        self.loaded: list[tuple[str, str]] = []
        self.unloaded = False
        self.load_side_effect: Exception | None = None
        self.generate_side_effect: Exception | None = None

    def load(self, artifact_path: str, base_model: str) -> None:
        if self.load_side_effect is not None:
            raise self.load_side_effect
        self.loaded.append((artifact_path, base_model))

    def generate(self, prompt: str, **kwargs) -> str:  # noqa: ARG002
        if self.generate_side_effect is not None:
            raise self.generate_side_effect
        return self.response

    def unload(self) -> None:
        self.unloaded = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_user(
    db_session: AsyncSession,
    *,
    email: str = "deployer@example.com",
) -> uuid.UUID:
    """Seed a user and return the id."""
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
    db_session: AsyncSession,
    user_id: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Seed a dataset + version. Return (dataset_id, version_id)."""
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
        f.write("instruction,response\n")
        f.write("What is 2+2?,4\n")

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
    """Seed a COMPLETED training job and return its id."""
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
    """Seed a COMPLETED evaluation and return its id."""
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
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Return (model_id, version_id, job_id, eval_id)."""
    ds_id, dver_id = await _seed_dataset(db_session, user_id)
    job_id = await _seed_completed_job(
        db_session, user_id, ds_id, dver_id, artifact_path
    )
    eval_id = await _seed_completed_evaluation(
        db_session, user_id, ds_id, dver_id, job_id
    )

    model = Model(owner_id=user_id, name="Test Model", description="desc")
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

    return model.id, version.id, job_id, eval_id


async def _register_and_login(client: AsyncClient) -> dict:
    payload = {
        "email": "deployer@example.com",
        "username": "deployer",
        "password": "StrongPass123!",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _register_user(
    client: AsyncClient, email: str, username: str
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
def override_deployment_service():
    """Override the deployment service dependency (uses real repos + test DB)."""
    from fastapi import Depends
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.session import get_db

    fake_inference = FakeInferenceService()

    def _make_service(
        db: AsyncSession = Depends(get_db),
    ) -> DeploymentService:
        return DeploymentService(
            deployment_repo=DeploymentRepository(db),
            model_repo=ModelRepository(db),
            training_job_repo=TrainingJobRepository(db),
            inference_service=fake_inference,
        )

    app.dependency_overrides[_get_deployment_service] = _make_service
    yield fake_inference
    app.dependency_overrides.pop(_get_deployment_service, None)


# ---------------------------------------------------------------------------
# Repository tests
# ---------------------------------------------------------------------------


class TestDeploymentRepository:
    async def test_create_and_get_deployment(self, db_session: AsyncSession):
        user_id = await _seed_user(db_session)
        _, version_id, _, _ = await _seed_model_version(db_session, user_id)

        repo = DeploymentRepository(db_session)
        deployment = Deployment(
            owner_id=user_id,
            model_version_id=version_id,
            deployment_name="prod-bot",
            endpoint_name="prod-bot-v1",
            status=DeploymentStatus.PENDING,
        )
        created = await repo.create_deployment(deployment)
        await repo.commit()

        fetched = await repo.get_deployment(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.status == DeploymentStatus.PENDING

    async def test_list_deployments(self, db_session: AsyncSession):
        user_id = await _seed_user(db_session)
        _, version_id, _, _ = await _seed_model_version(db_session, user_id)

        repo = DeploymentRepository(db_session)
        for i in range(3):
            d = Deployment(
                owner_id=user_id,
                model_version_id=version_id,
                deployment_name=f"d{i}",
                endpoint_name=f"e{i}",
            )
            await repo.create_deployment(d)
        await repo.commit()

        items = await repo.list_deployments(user_id, limit=10, offset=0)
        assert len(items) == 3

    async def test_update_status(self, db_session: AsyncSession):
        user_id = await _seed_user(db_session)
        _, version_id, _, _ = await _seed_model_version(db_session, user_id)

        repo = DeploymentRepository(db_session)
        deployment = Deployment(
            owner_id=user_id,
            model_version_id=version_id,
            deployment_name="d",
            endpoint_name="e",
        )
        deployment = await repo.create_deployment(deployment)
        await repo.commit()

        updated = await repo.update_status(deployment, DeploymentStatus.ACTIVE)
        assert updated.status == DeploymentStatus.ACTIVE
        await repo.commit()

        fetched = await repo.get_deployment(deployment.id)
        assert fetched is not None
        assert fetched.status == DeploymentStatus.ACTIVE

    async def test_find_active_deployment(self, db_session: AsyncSession):
        user_id = await _seed_user(db_session)
        _, version_id, _, _ = await _seed_model_version(db_session, user_id)

        repo = DeploymentRepository(db_session)
        active = Deployment(
            owner_id=user_id,
            model_version_id=version_id,
            deployment_name="active",
            endpoint_name="active",
            status=DeploymentStatus.ACTIVE,
        )
        await repo.create_deployment(active)
        await repo.commit()

        found = await repo.find_active_deployment(
            owner_id=user_id, model_version_id=version_id
        )
        assert found is not None
        assert found.status == DeploymentStatus.ACTIVE

        not_found = await repo.find_active_deployment(
            owner_id=uuid.uuid4(), model_version_id=version_id
        )
        assert not_found is None


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------


class TestDeploymentService:
    async def test_create_deployment_success(self, db_session: AsyncSession):
        user_id = await _seed_user(db_session)
        _, version_id, _, _ = await _seed_model_version(db_session, user_id)

        service = DeploymentService(
            deployment_repo=DeploymentRepository(db_session),
            model_repo=ModelRepository(db_session),
            training_job_repo=TrainingJobRepository(db_session),
            inference_service=FakeInferenceService(),
        )

        request = DeploymentCreateRequest(
            model_version_id=version_id,
            deployment_name="prod",
            endpoint_name="prod-v1",
        )
        result = await service.create_deployment(
            user_id=user_id, request=request
        )
        assert result.model_version_id == version_id
        assert result.status == DeploymentStatus.PENDING
        assert result.deployment_name == "prod"

    async def test_create_deployment_version_not_found(
        self, db_session: AsyncSession
    ):
        user_id = await _seed_user(db_session)
        service = DeploymentService(
            deployment_repo=DeploymentRepository(db_session),
            model_repo=ModelRepository(db_session),
            training_job_repo=TrainingJobRepository(db_session),
            inference_service=FakeInferenceService(),
        )
        request = DeploymentCreateRequest(
            model_version_id=uuid.uuid4(),
            deployment_name="prod",
            endpoint_name="prod-v1",
        )
        with pytest.raises(DeploymentModelVersionNotFoundError):
            await service.create_deployment(user_id=user_id, request=request)

    async def test_create_deployment_version_archived(
        self, db_session: AsyncSession
    ):
        user_id = await _seed_user(db_session)
        _, version_id, _, _ = await _seed_model_version(
            db_session, user_id, status=ModelVersionStatus.ARCHIVED
        )
        service = DeploymentService(
            deployment_repo=DeploymentRepository(db_session),
            model_repo=ModelRepository(db_session),
            training_job_repo=TrainingJobRepository(db_session),
            inference_service=FakeInferenceService(),
        )
        request = DeploymentCreateRequest(
            model_version_id=version_id,
            deployment_name="prod",
            endpoint_name="prod-v1",
        )
        with pytest.raises(DeploymentModelVersionArchivedError):
            await service.create_deployment(user_id=user_id, request=request)

    async def test_create_deployment_already_active(
        self, db_session: AsyncSession
    ):
        user_id = await _seed_user(db_session)
        _, version_id, _, _ = await _seed_model_version(db_session, user_id)

        repo = DeploymentRepository(db_session)
        active = Deployment(
            owner_id=user_id,
            model_version_id=version_id,
            deployment_name="active",
            endpoint_name="active",
            status=DeploymentStatus.ACTIVE,
        )
        await repo.create_deployment(active)
        await repo.commit()

        service = DeploymentService(
            deployment_repo=DeploymentRepository(db_session),
            model_repo=ModelRepository(db_session),
            training_job_repo=TrainingJobRepository(db_session),
            inference_service=FakeInferenceService(),
        )
        request = DeploymentCreateRequest(
            model_version_id=version_id,
            deployment_name="second",
            endpoint_name="second",
        )
        with pytest.raises(DeploymentAlreadyActiveError):
            await service.create_deployment(user_id=user_id, request=request)

    async def test_create_deployment_access_denied_for_other_user(
        self, db_session: AsyncSession
    ):
        user_a = await _seed_user(db_session, email="a@example.com")
        user_b = await _seed_user(db_session, email="b@example.com")
        _, version_id, _, _ = await _seed_model_version(db_session, user_a)

        service = DeploymentService(
            deployment_repo=DeploymentRepository(db_session),
            model_repo=ModelRepository(db_session),
            training_job_repo=TrainingJobRepository(db_session),
            inference_service=FakeInferenceService(),
        )
        request = DeploymentCreateRequest(
            model_version_id=version_id,
            deployment_name="prod",
            endpoint_name="prod-v1",
        )
        with pytest.raises(DeploymentModelVersionNotFoundError):
            await service.create_deployment(user_id=user_b, request=request)

    async def test_activate_deployment_success(self, db_session: AsyncSession):
        user_id = await _seed_user(db_session)
        artifact_dir = tempfile.mkdtemp()
        _, version_id, _, _ = await _seed_model_version(
            db_session, user_id, artifact_path=artifact_dir
        )

        fake_inference = FakeInferenceService()
        service = DeploymentService(
            deployment_repo=DeploymentRepository(db_session),
            model_repo=ModelRepository(db_session),
            training_job_repo=TrainingJobRepository(db_session),
            inference_service=fake_inference,
        )

        deployment = Deployment(
            owner_id=user_id,
            model_version_id=version_id,
            deployment_name="prod",
            endpoint_name="prod-v1",
        )
        repo = DeploymentRepository(db_session)
        deployment = await repo.create_deployment(deployment)
        await repo.commit()

        result = await service.activate_deployment(
            deployment.id, user_id=user_id
        )
        assert result.status == DeploymentStatus.ACTIVE
        assert len(fake_inference.loaded) == 1

    async def test_activate_deployment_missing_adapter(
        self, db_session: AsyncSession
    ):
        user_id = await _seed_user(db_session)
        _, version_id, _, _ = await _seed_model_version(
            db_session, user_id, artifact_path="/does/not/exist"
        )

        service = DeploymentService(
            deployment_repo=DeploymentRepository(db_session),
            model_repo=ModelRepository(db_session),
            training_job_repo=TrainingJobRepository(db_session),
            inference_service=FakeInferenceService(),
        )

        deployment = Deployment(
            owner_id=user_id,
            model_version_id=version_id,
            deployment_name="prod",
            endpoint_name="prod-v1",
        )
        repo = DeploymentRepository(db_session)
        deployment = await repo.create_deployment(deployment)
        await repo.commit()

        with pytest.raises(DeploymentAdapterNotFoundError):
            await service.activate_deployment(deployment.id, user_id=user_id)

    async def test_activate_deployment_already_active(
        self, db_session: AsyncSession
    ):
        user_id = await _seed_user(db_session)
        _, version_id, _, _ = await _seed_model_version(db_session, user_id)

        repo = DeploymentRepository(db_session)
        deployment = Deployment(
            owner_id=user_id,
            model_version_id=version_id,
            deployment_name="prod",
            endpoint_name="prod-v1",
            status=DeploymentStatus.ACTIVE,
        )
        deployment = await repo.create_deployment(deployment)
        await repo.commit()

        service = DeploymentService(
            deployment_repo=DeploymentRepository(db_session),
            model_repo=ModelRepository(db_session),
            training_job_repo=TrainingJobRepository(db_session),
            inference_service=FakeInferenceService(),
        )
        with pytest.raises(DeploymentAlreadyActiveError):
            await service.activate_deployment(deployment.id, user_id=user_id)

    async def test_activate_deployment_load_failure_marks_failed(
        self, db_session: AsyncSession
    ):
        user_id = await _seed_user(db_session)
        artifact_dir = tempfile.mkdtemp()
        _, version_id, _, _ = await _seed_model_version(
            db_session, user_id, artifact_path=artifact_dir
        )

        fake_inference = FakeInferenceService()
        fake_inference.load_side_effect = InferenceError("load failed")
        service = DeploymentService(
            deployment_repo=DeploymentRepository(db_session),
            model_repo=ModelRepository(db_session),
            training_job_repo=TrainingJobRepository(db_session),
            inference_service=fake_inference,
        )

        deployment = Deployment(
            owner_id=user_id,
            model_version_id=version_id,
            deployment_name="prod",
            endpoint_name="prod-v1",
        )
        repo = DeploymentRepository(db_session)
        deployment = await repo.create_deployment(deployment)
        await repo.commit()

        with pytest.raises(DeploymentError):
            await service.activate_deployment(deployment.id, user_id=user_id)

        # Refresh after service commits FAILED state
        fetched = await repo.get_deployment(deployment.id)
        assert fetched is not None
        assert fetched.status == DeploymentStatus.FAILED

    async def test_generate_success(self, db_session: AsyncSession):
        user_id = await _seed_user(db_session)
        artifact_dir = tempfile.mkdtemp()
        _, version_id, _, _ = await _seed_model_version(
            db_session, user_id, artifact_path=artifact_dir
        )

        fake_inference = FakeInferenceService(response="42")
        service = DeploymentService(
            deployment_repo=DeploymentRepository(db_session),
            model_repo=ModelRepository(db_session),
            training_job_repo=TrainingJobRepository(db_session),
            inference_service=fake_inference,
        )

        repo = DeploymentRepository(db_session)
        deployment = Deployment(
            owner_id=user_id,
            model_version_id=version_id,
            deployment_name="prod",
            endpoint_name="prod-v1",
            status=DeploymentStatus.ACTIVE,
        )
        deployment = await repo.create_deployment(deployment)
        await repo.commit()

        result = await service.generate(
            deployment.id,
            user_id=user_id,
            request=GenerateRequest.model_construct(prompt="answer"),
        )
        assert result.response == "42"

    async def test_generate_not_active(self, db_session: AsyncSession):
        user_id = await _seed_user(db_session)
        _, version_id, _, _ = await _seed_model_version(db_session, user_id)

        service = DeploymentService(
            deployment_repo=DeploymentRepository(db_session),
            model_repo=ModelRepository(db_session),
            training_job_repo=TrainingJobRepository(db_session),
            inference_service=FakeInferenceService(),
        )

        repo = DeploymentRepository(db_session)
        deployment = Deployment(
            owner_id=user_id,
            model_version_id=version_id,
            deployment_name="prod",
            endpoint_name="prod-v1",
            status=DeploymentStatus.PENDING,
        )
        deployment = await repo.create_deployment(deployment)
        await repo.commit()

        with pytest.raises(DeploymentNotActiveError):
            await service.generate(
                deployment.id,
                user_id=user_id,
                request=GenerateRequest.model_construct(prompt="hi"),
            )

    async def test_get_deployment_access_denied(
        self, db_session: AsyncSession
    ):
        user_a = await _seed_user(db_session, email="a2@example.com")
        user_b = await _seed_user(db_session, email="b2@example.com")
        _, version_id, _, _ = await _seed_model_version(db_session, user_a)

        repo = DeploymentRepository(db_session)
        deployment = Deployment(
            owner_id=user_a,
            model_version_id=version_id,
            deployment_name="prod",
            endpoint_name="prod-v1",
        )
        deployment = await repo.create_deployment(deployment)
        await repo.commit()

        service = DeploymentService(
            deployment_repo=DeploymentRepository(db_session),
            model_repo=ModelRepository(db_session),
            training_job_repo=TrainingJobRepository(db_session),
            inference_service=FakeInferenceService(),
        )
        with pytest.raises(DeploymentAccessDeniedError):
            await service.get_deployment(deployment.id, user_id=user_b)


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


class TestDeploymentAPI:
    async def test_create_deployment_endpoint(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
    ):
        result = await db_session.execute(
            select(User).where(User.email == "deployer@example.com")
        )
        user_id = result.scalar_one().id
        _, version_id, _, _ = await _seed_model_version(
            db_session, user_id, artifact_path="/tmp/adapter"
        )

        payload = {
            "model_version_id": str(version_id),
            "deployment_name": "prod-bot",
            "endpoint_name": "prod-bot-v1",
        }
        resp = await client.post(
            "/api/v1/deployments",
            json=payload,
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        assert data["deployment_name"] == "prod-bot"
        assert data["status"] == "pending"

    async def test_list_and_get_deployment_endpoints(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
    ):
        result = await db_session.execute(
            select(User).where(User.email == "deployer@example.com")
        )
        user_id = result.scalar_one().id
        _, version_id, _, _ = await _seed_model_version(
            db_session, user_id, artifact_path="/tmp/adapter2"
        )

        payload = {
            "model_version_id": str(version_id),
            "deployment_name": "list-bot",
            "endpoint_name": "list-bot-v1",
        }
        create_resp = await client.post(
            "/api/v1/deployments", json=payload, headers=auth_headers
        )
        deployment_id = create_resp.json()["data"]["id"]

        list_resp = await client.get(
            "/api/v1/deployments", headers=auth_headers
        )
        assert list_resp.status_code == 200
        assert list_resp.json()["data"]["total"] >= 1

        get_resp = await client.get(
            f"/api/v1/deployments/{deployment_id}", headers=auth_headers
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["data"]["id"] == deployment_id

    async def test_activate_and_generate_endpoints(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        override_deployment_service: FakeInferenceService,
    ):
        result = await db_session.execute(
            select(User).where(User.email == "deployer@example.com")
        )
        user_id = result.scalar_one().id
        artifact_dir = tempfile.mkdtemp()
        _, version_id, _, _ = await _seed_model_version(
            db_session, user_id, artifact_path=artifact_dir
        )

        payload = {
            "model_version_id": str(version_id),
            "deployment_name": "infer-bot",
            "endpoint_name": "infer-bot-v1",
        }
        create_resp = await client.post(
            "/api/v1/deployments", json=payload, headers=auth_headers
        )
        deployment_id = create_resp.json()["data"]["id"]

        activate_resp = await client.post(
            f"/api/v1/deployments/{deployment_id}/activate",
            headers=auth_headers,
        )
        assert activate_resp.status_code == 200, activate_resp.text
        assert activate_resp.json()["data"]["status"] == "active"
        assert len(override_deployment_service.loaded) == 1

        gen_resp = await client.post(
            f"/api/v1/deployments/{deployment_id}/generate",
            json={"prompt": "What is 2+2?"},
            headers=auth_headers,
        )
        assert gen_resp.status_code == 200, gen_resp.text
        assert gen_resp.json()["data"]["response"] == "mock response"

    async def test_generate_before_active_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
    ):
        result = await db_session.execute(
            select(User).where(User.email == "deployer@example.com")
        )
        user_id = result.scalar_one().id
        _, version_id, _, _ = await _seed_model_version(
            db_session, user_id, artifact_path="/tmp/adapter3"
        )

        payload = {
            "model_version_id": str(version_id),
            "deployment_name": "pending-bot",
            "endpoint_name": "pending-bot-v1",
        }
        create_resp = await client.post(
            "/api/v1/deployments", json=payload, headers=auth_headers
        )
        deployment_id = create_resp.json()["data"]["id"]

        gen_resp = await client.post(
            f"/api/v1/deployments/{deployment_id}/generate",
            json={"prompt": "hi"},
            headers=auth_headers,
        )
        assert gen_resp.status_code == 409
        assert gen_resp.json()["success"] is False
        assert gen_resp.json()["error"]["code"] == "DEPLOYMENT_NOT_ACTIVE"

    async def test_get_deployment_not_found(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.get(
            f"/api/v1/deployments/{uuid.uuid4()}", headers=auth_headers
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "DEPLOYMENT_NOT_FOUND"

    async def test_create_deployment_requires_auth(
        self, client: AsyncClient
    ):
        resp = await client.post(
            "/api/v1/deployments",
            json={
                "model_version_id": str(uuid.uuid4()),
                "deployment_name": "x",
                "endpoint_name": "x",
            },
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# InferenceService unit tests (mocked, no real model loading)
# ---------------------------------------------------------------------------


class TestInferenceService:
    def test_inference_service_initial_state(self):
        service = InferenceService()
        assert service.is_loaded is False
        assert service._key is None

    def test_generate_without_load_raises(self):
        service = InferenceService()
        with pytest.raises(InferenceError):
            service.generate("hello")

    def test_unload_clears_cache(self):
        service = InferenceService()
        service._model = object()
        service._tokenizer = object()
        service._key = "k"
        service.unload()
        assert service.is_loaded is False
        assert service._key is None
