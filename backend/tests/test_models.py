"""Tests for the Model Registry.

Covers:
- Model and ModelVersion repository operations
- ModelRegistryService business rules (lifecycle, ownership, validation)
- API endpoints (POST/GET model, POST version, POST promote/archive)
- One-PRODUCTION-version invariant
- Invalid transitions and access control
"""

from __future__ import annotations

import tempfile
import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.models import _get_model_registry_service
from app.main import app
from app.models.dataset import (
    Dataset,
    DatasetFormat,
    DatasetStatus,
    DatasetType,
    DatasetVersion,
)
from app.models.evaluation import Evaluation, EvaluationStatus
from app.models.model import Model, ModelVersion, ModelVersionStatus
from app.models.training_job import TrainingJob, TrainingJobStatus, TrainingType
from app.models.user import User
from app.repositories.evaluation_repository import EvaluationRepository
from app.repositories.model_repository import ModelRepository
from app.repositories.training_job_repository import TrainingJobRepository
from app.services.model_registry_service import (
    EvaluationNotFoundError as RegistryEvaluationNotFoundError,
    EvaluationNotReadyError as RegistryEvaluationNotReadyError,
    InvalidArchiveError,
    InvalidPromotionError,
    ModelAccessDeniedError,
    ModelNotFoundError,
    ModelRegistryService,
    ModelVersionAccessDeniedError,
    ModelVersionExistsError,
    ModelVersionNotFoundError,
    TrainingJobNotFoundError as RegistryTrainingJobNotFoundError,
    TrainingJobNotReadyError as RegistryTrainingJobNotReadyError,
)
from app.core.security import hash_password


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_user(
    db_session: AsyncSession,
    *,
    email: str = "modeler@example.com",
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
) -> tuple[uuid.UUID, uuid.UUID, str]:
    """Seed a dataset + version. Return (dataset_id, version_id, file_path)."""
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
    return ds.id, ver.id, path


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


async def _seed_model(
    db_session: AsyncSession,
    user_id: uuid.UUID,
    name: str = "Test Model",
) -> uuid.UUID:
    """Seed a model container and return its id."""
    model = Model(owner_id=user_id, name=name, description="desc")
    repo = ModelRepository(db_session)
    await repo.create_model(model)
    await repo.commit()
    return model.id


async def _seed_full_registry_stack(
    db_session: AsyncSession,
    user_id: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Return (model_id, job_id, evaluation_id, version_id)."""
    ds_id, ver_id, _ = await _seed_dataset(db_session, user_id)
    job_id = await _seed_completed_job(
        db_session, user_id, ds_id, ver_id, "/tmp/adapter"
    )
    eval_id = await _seed_completed_evaluation(
        db_session, user_id, ds_id, ver_id, job_id
    )
    model_id = await _seed_model(db_session, user_id)
    return model_id, job_id, eval_id, ds_id, ver_id


async def _register_and_login(client: AsyncClient) -> dict:
    payload = {
        "email": "modeler@example.com",
        "username": "modeler",
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
def override_registry_service():
    """Override the registry service dependency (uses real repos + test DB)."""
    from fastapi import Depends
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.session import get_db

    def _make_service(
        db: AsyncSession = Depends(get_db),
    ) -> ModelRegistryService:
        return ModelRegistryService(
            model_repo=ModelRepository(db),
            training_job_repo=TrainingJobRepository(db),
            evaluation_repo=EvaluationRepository(db),
        )

    app.dependency_overrides[_get_model_registry_service] = _make_service
    yield
    app.dependency_overrides.pop(_get_model_registry_service, None)


# ---------------------------------------------------------------------------
# Repository tests
# ---------------------------------------------------------------------------


class TestModelRepository:
    """Direct repository operations against the test DB."""

    async def test_create_and_get_model(self, db_session: AsyncSession):
        user_id = await _seed_user(db_session, email="repo1@example.com")
        repo = ModelRepository(db_session)
        model = Model(owner_id=user_id, name="M1", description="d")
        created = await repo.create_model(model)
        await repo.commit()

        fetched = await repo.get_model(created.id)
        assert fetched is not None
        assert fetched.name == "M1"
        assert fetched.owner_id == user_id

    async def test_list_and_count_models(self, db_session: AsyncSession):
        user_id = await _seed_user(db_session, email="repo2@example.com")
        other_id = await _seed_user(db_session, email="repo2other@example.com")
        repo = ModelRepository(db_session)

        await repo.create_model(Model(owner_id=user_id, name="M1"))
        await repo.create_model(Model(owner_id=user_id, name="M2"))
        await repo.create_model(Model(owner_id=other_id, name="M3"))
        await repo.commit()

        items = await repo.list_models(user_id, limit=10, offset=0)
        assert len(items) == 2
        assert await repo.count_models(user_id) == 2

    async def test_create_and_get_version(self, db_session: AsyncSession):
        user_id = await _seed_user(db_session, email="repo3@example.com")
        model_id, job_id, eval_id, _, _ = await _seed_full_registry_stack(
            db_session, user_id
        )
        repo = ModelRepository(db_session)

        version = ModelVersion(
            model_id=model_id,
            training_job_id=job_id,
            evaluation_id=eval_id,
            version_number=1,
            artifact_path="/tmp/adapter",
            status=ModelVersionStatus.STAGING,
        )
        created = await repo.create_version(version)
        await repo.commit()

        fetched = await repo.get_version(created.id)
        assert fetched is not None
        assert fetched.version_number == 1
        assert fetched.status == ModelVersionStatus.STAGING

    async def test_get_next_version_number(self, db_session: AsyncSession):
        user_id = await _seed_user(db_session, email="repo4@example.com")
        model_id, job_id, eval_id, _, _ = await _seed_full_registry_stack(
            db_session, user_id
        )
        repo = ModelRepository(db_session)
        assert await repo.get_next_version_number(model_id) == 1

        await repo.create_version(
            ModelVersion(
                model_id=model_id,
                training_job_id=job_id,
                evaluation_id=eval_id,
                version_number=1,
                artifact_path="/tmp/a1",
            )
        )
        await repo.commit()
        assert await repo.get_next_version_number(model_id) == 2

    async def test_promote_version_demotes_current_production(
        self, db_session: AsyncSession
    ):
        user_id = await _seed_user(db_session, email="repo5@example.com")
        model_id, job_id, eval_id, ds_id, ver_id = await _seed_full_registry_stack(
            db_session, user_id
        )
        repo = ModelRepository(db_session)

        # Need a second training job + eval for v2
        job2_id = await _seed_completed_job(
            db_session, user_id, ds_id, ver_id, "/tmp/adapter2"
        )
        eval2_id = await _seed_completed_evaluation(
            db_session, user_id, ds_id, ver_id, job2_id
        )

        v1 = await repo.create_version(
            ModelVersion(
                model_id=model_id,
                training_job_id=job_id,
                evaluation_id=eval_id,
                version_number=1,
                artifact_path="/tmp/a1",
                status=ModelVersionStatus.PRODUCTION,
            )
        )
        v2 = await repo.create_version(
            ModelVersion(
                model_id=model_id,
                training_job_id=job2_id,
                evaluation_id=eval2_id,
                version_number=2,
                artifact_path="/tmp/a2",
                status=ModelVersionStatus.STAGING,
            )
        )
        await repo.commit()

        promoted = await repo.promote_version(v2.id)
        await repo.commit()

        assert promoted is not None
        assert promoted.status == ModelVersionStatus.PRODUCTION

        refreshed_v1 = await repo.get_version(v1.id)
        assert refreshed_v1 is not None
        assert refreshed_v1.status == ModelVersionStatus.STAGING

    async def test_archive_version(self, db_session: AsyncSession):
        user_id = await _seed_user(db_session, email="repo6@example.com")
        model_id, job_id, eval_id, _, _ = await _seed_full_registry_stack(
            db_session, user_id
        )
        repo = ModelRepository(db_session)
        version = await repo.create_version(
            ModelVersion(
                model_id=model_id,
                training_job_id=job_id,
                evaluation_id=eval_id,
                version_number=1,
                artifact_path="/tmp/a1",
                status=ModelVersionStatus.STAGING,
            )
        )
        await repo.commit()

        archived = await repo.archive_version(version.id)
        await repo.commit()
        assert archived is not None
        assert archived.status == ModelVersionStatus.ARCHIVED


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------


class TestModelRegistryService:
    """Business rule tests against the test DB."""

    @pytest.fixture
    def service(self, db_session: AsyncSession) -> ModelRegistryService:
        return ModelRegistryService(
            model_repo=ModelRepository(db_session),
            training_job_repo=TrainingJobRepository(db_session),
            evaluation_repo=EvaluationRepository(db_session),
        )

    async def test_create_model(self, db_session: AsyncSession, service):
        user_id = await _seed_user(db_session, email="svc1@example.com")
        from app.schemas.model import ModelCreateRequest

        resp = await service.create_model(
            user_id=user_id,
            request=ModelCreateRequest(name="Svc Model", description="d"),
        )
        assert resp.name == "Svc Model"
        assert resp.owner_id == user_id

    async def test_get_model_not_found(self, db_session: AsyncSession, service):
        user_id = await _seed_user(db_session, email="svc2@example.com")
        with pytest.raises(ModelNotFoundError):
            await service.get_model(uuid.uuid4(), user_id=user_id)

    async def test_get_model_access_denied(
        self, db_session: AsyncSession, service
    ):
        owner_id = await _seed_user(db_session, email="svc3owner@example.com")
        other_id = await _seed_user(db_session, email="svc3other@example.com")
        model_id = await _seed_model(db_session, owner_id)
        with pytest.raises(ModelAccessDeniedError):
            await service.get_model(model_id, user_id=other_id)

    async def test_list_models(self, db_session: AsyncSession, service):
        user_id = await _seed_user(db_session, email="svc4@example.com")
        await _seed_model(db_session, user_id, "M1")
        await _seed_model(db_session, user_id, "M2")
        resp = await service.list_models(user_id=user_id)
        assert resp.total == 2
        assert len(resp.items) == 2

    async def test_create_version_success(
        self, db_session: AsyncSession, service
    ):
        user_id = await _seed_user(db_session, email="svc5@example.com")
        model_id, job_id, eval_id, _, _ = await _seed_full_registry_stack(
            db_session, user_id
        )
        from app.schemas.model import ModelVersionCreateRequest

        resp = await service.create_version(
            user_id=user_id,
            model_id=model_id,
            request=ModelVersionCreateRequest(
                training_job_id=job_id, evaluation_id=eval_id
            ),
        )
        assert resp.model_id == model_id
        assert resp.version_number == 1
        assert resp.status == ModelVersionStatus.STAGING
        assert resp.artifact_path == "/tmp/adapter"
        assert resp.metrics_snapshot["bertscore_f1"] == 0.84

    async def test_create_version_model_not_found(
        self, db_session: AsyncSession, service
    ):
        user_id = await _seed_user(db_session, email="svc6@example.com")
        model_id, job_id, eval_id, _, _ = await _seed_full_registry_stack(
            db_session, user_id
        )
        from app.schemas.model import ModelVersionCreateRequest

        with pytest.raises(ModelNotFoundError):
            await service.create_version(
                user_id=user_id,
                model_id=uuid.uuid4(),
                request=ModelVersionCreateRequest(
                    training_job_id=job_id, evaluation_id=eval_id
                ),
            )

    async def test_create_version_model_access_denied(
        self, db_session: AsyncSession, service
    ):
        owner_id = await _seed_user(db_session, email="svc7owner@example.com")
        other_id = await _seed_user(db_session, email="svc7other@example.com")
        model_id, job_id, eval_id, _, _ = await _seed_full_registry_stack(
            db_session, owner_id
        )
        from app.schemas.model import ModelVersionCreateRequest

        with pytest.raises(ModelAccessDeniedError):
            await service.create_version(
                user_id=other_id,
                model_id=model_id,
                request=ModelVersionCreateRequest(
                    training_job_id=job_id, evaluation_id=eval_id
                ),
            )

    async def test_create_version_training_job_not_found(
        self, db_session: AsyncSession, service
    ):
        user_id = await _seed_user(db_session, email="svc8@example.com")
        model_id, job_id, eval_id, _, _ = await _seed_full_registry_stack(
            db_session, user_id
        )
        from app.schemas.model import ModelVersionCreateRequest

        with pytest.raises(RegistryTrainingJobNotFoundError):
            await service.create_version(
                user_id=user_id,
                model_id=model_id,
                request=ModelVersionCreateRequest(
                    training_job_id=uuid.uuid4(), evaluation_id=eval_id
                ),
            )

    async def test_create_version_training_job_not_ready(
        self, db_session: AsyncSession, service
    ):
        user_id = await _seed_user(db_session, email="svc9@example.com")
        model_id, job_id, eval_id, ds_id, ver_id = await _seed_full_registry_stack(
            db_session, user_id
        )
        # Create a second job that is still queued
        queued_job = TrainingJob(
            user_id=user_id,
            dataset_id=ds_id,
            dataset_version_id=ver_id,
            base_model="google/gemma-3-1b-it",
            training_type=TrainingType.QLORA,
            configuration={"epochs": 1, "batch_size": 2, "learning_rate": 2e-4, "max_seq_length": 512},
            status=TrainingJobStatus.QUEUED,
        )
        repo = TrainingJobRepository(db_session)
        await repo.create(queued_job)
        await repo.commit()

        from app.schemas.model import ModelVersionCreateRequest
        with pytest.raises(RegistryTrainingJobNotReadyError):
            await service.create_version(
                user_id=user_id,
                model_id=model_id,
                request=ModelVersionCreateRequest(
                    training_job_id=queued_job.id, evaluation_id=eval_id
                ),
            )

    async def test_create_version_evaluation_not_found(
        self, db_session: AsyncSession, service
    ):
        user_id = await _seed_user(db_session, email="svc10@example.com")
        model_id, job_id, eval_id, _, _ = await _seed_full_registry_stack(
            db_session, user_id
        )
        from app.schemas.model import ModelVersionCreateRequest

        with pytest.raises(RegistryEvaluationNotFoundError):
            await service.create_version(
                user_id=user_id,
                model_id=model_id,
                request=ModelVersionCreateRequest(
                    training_job_id=job_id, evaluation_id=uuid.uuid4()
                ),
            )

    async def test_create_version_evaluation_not_ready(
        self, db_session: AsyncSession, service
    ):
        user_id = await _seed_user(db_session, email="svc11@example.com")
        model_id, job_id, eval_id, ds_id, ver_id = await _seed_full_registry_stack(
            db_session, user_id
        )
        # Create a running evaluation for the same job
        running_eval = Evaluation(
            user_id=user_id,
            dataset_id=ds_id,
            dataset_version_id=ver_id,
            model_id=job_id,
            status=EvaluationStatus.RUNNING,
        )
        repo = EvaluationRepository(db_session)
        await repo.create(running_eval)
        await repo.commit()

        from app.schemas.model import ModelVersionCreateRequest
        with pytest.raises(RegistryEvaluationNotReadyError):
            await service.create_version(
                user_id=user_id,
                model_id=model_id,
                request=ModelVersionCreateRequest(
                    training_job_id=job_id, evaluation_id=running_eval.id
                ),
            )

    async def test_create_version_evaluation_mismatch(
        self, db_session: AsyncSession, service
    ):
        user_id = await _seed_user(db_session, email="svc12@example.com")
        model_id, job_id, eval_id, ds_id, ver_id = await _seed_full_registry_stack(
            db_session, user_id
        )
        # Create a second completed job + eval
        job2_id = await _seed_completed_job(
            db_session, user_id, ds_id, ver_id, "/tmp/adapter2"
        )
        # eval_id belongs to job_id, but request uses job2_id
        from app.schemas.model import ModelVersionCreateRequest

        with pytest.raises(Exception) as exc_info:
            await service.create_version(
                user_id=user_id,
                model_id=model_id,
                request=ModelVersionCreateRequest(
                    training_job_id=job2_id, evaluation_id=eval_id
                ),
            )
        assert "does not belong to" in str(exc_info.value)

    async def test_promote_version_success(
        self, db_session: AsyncSession, service
    ):
        user_id = await _seed_user(db_session, email="svc13@example.com")
        model_id, job_id, eval_id, _, _ = await _seed_full_registry_stack(
            db_session, user_id
        )
        from app.schemas.model import ModelVersionCreateRequest

        v1 = await service.create_version(
            user_id=user_id,
            model_id=model_id,
            request=ModelVersionCreateRequest(
                training_job_id=job_id, evaluation_id=eval_id
            ),
        )
        promoted = await service.promote_version(v1.id, user_id=user_id)
        assert promoted.status == ModelVersionStatus.PRODUCTION

    async def test_promote_archived_version_fails(
        self, db_session: AsyncSession, service
    ):
        user_id = await _seed_user(db_session, email="svc14@example.com")
        model_id, job_id, eval_id, _, _ = await _seed_full_registry_stack(
            db_session, user_id
        )
        repo = ModelRepository(db_session)
        version = await repo.create_version(
            ModelVersion(
                model_id=model_id,
                training_job_id=job_id,
                evaluation_id=eval_id,
                version_number=1,
                artifact_path="/tmp/a1",
                status=ModelVersionStatus.ARCHIVED,
            )
        )
        await repo.commit()

        with pytest.raises(InvalidPromotionError):
            await service.promote_version(version.id, user_id=user_id)

    async def test_promote_already_production_fails(
        self, db_session: AsyncSession, service
    ):
        user_id = await _seed_user(db_session, email="svc15@example.com")
        model_id, job_id, eval_id, _, _ = await _seed_full_registry_stack(
            db_session, user_id
        )
        repo = ModelRepository(db_session)
        version = await repo.create_version(
            ModelVersion(
                model_id=model_id,
                training_job_id=job_id,
                evaluation_id=eval_id,
                version_number=1,
                artifact_path="/tmp/a1",
                status=ModelVersionStatus.PRODUCTION,
            )
        )
        await repo.commit()

        with pytest.raises(InvalidPromotionError):
            await service.promote_version(version.id, user_id=user_id)

    async def test_one_production_version_invariant(
        self, db_session: AsyncSession, service
    ):
        user_id = await _seed_user(db_session, email="svc16@example.com")
        model_id, job_id, eval_id, ds_id, ver_id = await _seed_full_registry_stack(
            db_session, user_id
        )
        from app.schemas.model import ModelVersionCreateRequest

        v1 = await service.create_version(
            user_id=user_id,
            model_id=model_id,
            request=ModelVersionCreateRequest(
                training_job_id=job_id, evaluation_id=eval_id
            ),
        )
        await service.promote_version(v1.id, user_id=user_id)

        # Create v2 with a new job+eval
        job2_id = await _seed_completed_job(
            db_session, user_id, ds_id, ver_id, "/tmp/adapter2"
        )
        eval2_id = await _seed_completed_evaluation(
            db_session, user_id, ds_id, ver_id, job2_id
        )
        v2 = await service.create_version(
            user_id=user_id,
            model_id=model_id,
            request=ModelVersionCreateRequest(
                training_job_id=job2_id, evaluation_id=eval2_id
            ),
        )
        await service.promote_version(v2.id, user_id=user_id)

        model = await service.get_model(model_id, user_id=user_id)
        prod_versions = [v for v in model.versions if v.status == ModelVersionStatus.PRODUCTION]
        assert len(prod_versions) == 1
        assert prod_versions[0].id == v2.id

        v1_refreshed = next(v for v in model.versions if v.id == v1.id)
        assert v1_refreshed.status == ModelVersionStatus.STAGING

    async def test_archive_version(self, db_session: AsyncSession, service):
        user_id = await _seed_user(db_session, email="svc17@example.com")
        model_id, job_id, eval_id, _, _ = await _seed_full_registry_stack(
            db_session, user_id
        )
        from app.schemas.model import ModelVersionCreateRequest

        v1 = await service.create_version(
            user_id=user_id,
            model_id=model_id,
            request=ModelVersionCreateRequest(
                training_job_id=job_id, evaluation_id=eval_id
            ),
        )
        archived = await service.archive_version(v1.id, user_id=user_id)
        assert archived.status == ModelVersionStatus.ARCHIVED

    async def test_archive_already_archived_fails(
        self, db_session: AsyncSession, service
    ):
        user_id = await _seed_user(db_session, email="svc18@example.com")
        model_id, job_id, eval_id, _, _ = await _seed_full_registry_stack(
            db_session, user_id
        )
        repo = ModelRepository(db_session)
        version = await repo.create_version(
            ModelVersion(
                model_id=model_id,
                training_job_id=job_id,
                evaluation_id=eval_id,
                version_number=1,
                artifact_path="/tmp/a1",
                status=ModelVersionStatus.ARCHIVED,
            )
        )
        await repo.commit()

        with pytest.raises(InvalidArchiveError):
            await service.archive_version(version.id, user_id=user_id)

    async def test_version_access_denied(
        self, db_session: AsyncSession, service
    ):
        owner_id = await _seed_user(db_session, email="svc19owner@example.com")
        other_id = await _seed_user(db_session, email="svc19other@example.com")
        model_id, job_id, eval_id, _, _ = await _seed_full_registry_stack(
            db_session, owner_id
        )
        repo = ModelRepository(db_session)
        version = await repo.create_version(
            ModelVersion(
                model_id=model_id,
                training_job_id=job_id,
                evaluation_id=eval_id,
                version_number=1,
                artifact_path="/tmp/a1",
                status=ModelVersionStatus.STAGING,
            )
        )
        await repo.commit()

        with pytest.raises(ModelVersionAccessDeniedError):
            await service.promote_version(version.id, user_id=other_id)


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


class TestModelRegistryAPI:
    """End-to-end API tests via the async test client."""

    async def test_create_model_api(
        self, client: AsyncClient, auth_headers, override_registry_service
    ):
        resp = await client.post(
            "/api/v1/models",
            json={"name": "API Model", "description": "from api"},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        assert data["name"] == "API Model"
        assert data["owner_id"] is not None

    async def test_create_model_no_auth(
        self, client: AsyncClient, override_registry_service
    ):
        resp = await client.post(
            "/api/v1/models",
            json={"name": "No Auth"},
        )
        assert resp.status_code == 401
        assert resp.json()["success"] is False

    async def test_list_models_api(
        self, client: AsyncClient, auth_headers, override_registry_service
    ):
        await client.post(
            "/api/v1/models",
            json={"name": "M1"},
            headers=auth_headers,
        )
        await client.post(
            "/api/v1/models",
            json={"name": "M2"},
            headers=auth_headers,
        )
        resp = await client.get("/api/v1/models", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 2
        assert len(data["items"]) == 2

    async def test_get_model_api(
        self, client: AsyncClient, auth_headers, override_registry_service
    ):
        create_resp = await client.post(
            "/api/v1/models",
            json={"name": "Get Me"},
            headers=auth_headers,
        )
        model_id = create_resp.json()["data"]["id"]
        resp = await client.get(
            f"/api/v1/models/{model_id}", headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Get Me"

    async def test_get_model_not_found_api(
        self, client: AsyncClient, auth_headers, override_registry_service
    ):
        resp = await client.get(
            f"/api/v1/models/{uuid.uuid4()}", headers=auth_headers
        )
        assert resp.status_code == 404

    async def test_get_model_cross_user_isolated(
        self, client: AsyncClient, override_registry_service
    ):
        headers_a = await _register_user(client, "a@example.com", "usera")
        headers_b = await _register_user(client, "b@example.com", "userb")

        create_resp = await client.post(
            "/api/v1/models",
            json={"name": "Private"},
            headers=headers_a,
        )
        model_id = create_resp.json()["data"]["id"]

        resp = await client.get(
            f"/api/v1/models/{model_id}", headers=headers_b
        )
        assert resp.status_code == 403

    async def test_create_version_api_success(
        self, client: AsyncClient, override_registry_service, db_session
    ):
        # Register user via API to get a real token, then seed DB directly.
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "vapi@example.com",
                "username": "vapi",
                "password": "StrongPass123!",
            },
        )
        # Get the user id from DB
        from sqlalchemy import select

        result = await db_session.execute(
            select(User).where(User.email == "vapi@example.com")
        )
        user = result.scalar_one()
        model_id, job_id, eval_id, _, _ = await _seed_full_registry_stack(
            db_session, user.id
        )

        resp_login = await client.post(
            "/api/v1/auth/login",
            json={"email": "vapi@example.com", "password": "StrongPass123!"},
        )
        headers = {
            "Authorization": f"Bearer {resp_login.json()['data']['access_token']}"
        }

        resp = await client.post(
            f"/api/v1/models/{model_id}/versions",
            json={"training_job_id": str(job_id), "evaluation_id": str(eval_id)},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        assert data["version_number"] == 1
        assert data["status"] == "staging"

    async def test_promote_version_api(
        self, client: AsyncClient, override_registry_service, db_session
    ):
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "promapi@example.com",
                "username": "promapi",
                "password": "StrongPass123!",
            },
        )
        from sqlalchemy import select

        result = await db_session.execute(
            select(User).where(User.email == "promapi@example.com")
        )
        user = result.scalar_one()
        model_id, job_id, eval_id, _, _ = await _seed_full_registry_stack(
            db_session, user.id
        )

        repo = ModelRepository(db_session)
        version = await repo.create_version(
            ModelVersion(
                model_id=model_id,
                training_job_id=job_id,
                evaluation_id=eval_id,
                version_number=1,
                artifact_path="/tmp/a1",
                status=ModelVersionStatus.STAGING,
            )
        )
        await repo.commit()

        resp_login = await client.post(
            "/api/v1/auth/login",
            json={"email": "promapi@example.com", "password": "StrongPass123!"},
        )
        headers = {
            "Authorization": f"Bearer {resp_login.json()['data']['access_token']}"
        }

        resp = await client.post(
            f"/api/v1/models/versions/{version.id}/promote",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "production"

    async def test_archive_version_api(
        self, client: AsyncClient, override_registry_service, db_session
    ):
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "archapi@example.com",
                "username": "archapi",
                "password": "StrongPass123!",
            },
        )
        from sqlalchemy import select

        result = await db_session.execute(
            select(User).where(User.email == "archapi@example.com")
        )
        user = result.scalar_one()
        model_id, job_id, eval_id, _, _ = await _seed_full_registry_stack(
            db_session, user.id
        )

        repo = ModelRepository(db_session)
        version = await repo.create_version(
            ModelVersion(
                model_id=model_id,
                training_job_id=job_id,
                evaluation_id=eval_id,
                version_number=1,
                artifact_path="/tmp/a1",
                status=ModelVersionStatus.STAGING,
            )
        )
        await repo.commit()

        resp_login = await client.post(
            "/api/v1/auth/login",
            json={"email": "archapi@example.com", "password": "StrongPass123!"},
        )
        headers = {
            "Authorization": f"Bearer {resp_login.json()['data']['access_token']}"
        }

        resp = await client.post(
            f"/api/v1/models/versions/{version.id}/archive",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "archived"

    async def test_promote_archived_version_api(
        self, client: AsyncClient, override_registry_service, db_session
    ):
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "badpromapi@example.com",
                "username": "badpromapi",
                "password": "StrongPass123!",
            },
        )
        from sqlalchemy import select

        result = await db_session.execute(
            select(User).where(User.email == "badpromapi@example.com")
        )
        user = result.scalar_one()
        model_id, job_id, eval_id, _, _ = await _seed_full_registry_stack(
            db_session, user.id
        )

        repo = ModelRepository(db_session)
        version = await repo.create_version(
            ModelVersion(
                model_id=model_id,
                training_job_id=job_id,
                evaluation_id=eval_id,
                version_number=1,
                artifact_path="/tmp/a1",
                status=ModelVersionStatus.ARCHIVED,
            )
        )
        await repo.commit()

        resp_login = await client.post(
            "/api/v1/auth/login",
            json={"email": "badpromapi@example.com", "password": "StrongPass123!"},
        )
        headers = {
            "Authorization": f"Bearer {resp_login.json()['data']['access_token']}"
        }

        resp = await client.post(
            f"/api/v1/models/versions/{version.id}/promote",
            headers=headers,
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "INVALID_PROMOTION"

    async def test_create_version_invalid_job_api(
        self, client: AsyncClient, override_registry_service, db_session
    ):
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "badjobapi@example.com",
                "username": "badjobapi",
                "password": "StrongPass123!",
            },
        )
        from sqlalchemy import select

        result = await db_session.execute(
            select(User).where(User.email == "badjobapi@example.com")
        )
        user = result.scalar_one()
        model_id, job_id, eval_id, _, _ = await _seed_full_registry_stack(
            db_session, user.id
        )

        resp_login = await client.post(
            "/api/v1/auth/login",
            json={"email": "badjobapi@example.com", "password": "StrongPass123!"},
        )
        headers = {
            "Authorization": f"Bearer {resp_login.json()['data']['access_token']}"
        }

        resp = await client.post(
            f"/api/v1/models/{model_id}/versions",
            json={
                "training_job_id": str(uuid.uuid4()),
                "evaluation_id": str(eval_id),
            },
            headers=headers,
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "TRAINING_JOB_NOT_FOUND"

    async def test_create_model_extra_fields_rejected(
        self, client: AsyncClient, auth_headers, override_registry_service
    ):
        resp = await client.post(
            "/api/v1/models",
            json={"name": "Extra", "unexpected": "field"},
            headers=auth_headers,
        )
        assert resp.status_code == 422
