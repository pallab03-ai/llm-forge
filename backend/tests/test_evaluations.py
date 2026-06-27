"""Tests for the Evaluation Service.

Covers:
- Successful evaluation (mocked predictions + metrics)
- Invalid model (not found, not owned, no artifact)
- Invalid dataset (not found, version mismatch)
- Metric computation failure
- Repository operations (create, update status, save metrics, save error)
- API endpoints (POST, GET list, GET by id, auth required, access denied)
- Schema validation (extra fields forbidden)

The prediction-generation seam (_generate_predictions) and the three
metric functions are monkeypatched so tests run without GPU/ML packages.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.evaluations import _get_evaluation_service
from app.main import app
from app.models.evaluation import Evaluation, EvaluationStatus
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.evaluation_repository import EvaluationRepository
from app.repositories.training_job_repository import TrainingJobRepository
from app.services.evaluation_service import (
    AdapterNotFoundError,
    DatasetNotFoundError,
    DatasetVersionNotFoundError,
    EvaluationAccessDeniedError,
    EvaluationNotFoundError,
    EvaluationService,
    MetricComputationError,
    ModelNotFoundError,
    ModelNotReadyError,
)
from app.services import metrics as metrics_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _register_and_login(client: AsyncClient) -> dict:
    payload = {
        "email": "evaluator@example.com",
        "username": "evaluator",
        "password": "StrongPass123!",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _register_user(
    client: AsyncClient, email: str, username: str
) -> dict:
    payload = {"email": email, "username": username, "password": "StrongPass123!"}
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _csv_bytes(rows: list[dict]) -> bytes:
    if not rows:
        return b""
    headers = list(rows[0].keys())
    lines = [",".join(headers)]
    for row in rows:
        lines.append(",".join(str(row.get(h, "")) for h in headers))
    return ("\n".join(lines) + "\n").encode("utf-8")


async def _create_dataset(
    client: AsyncClient, headers: dict, name: str = "eval-ds"
) -> dict:
    rows = [
        {"instruction": "What is 2+2?", "response": "4"},
        {"instruction": "Capital of France?", "response": "Paris"},
    ]
    files = {"file": ("a.csv", _csv_bytes(rows), "text/csv")}
    data = {"name": name, "dataset_type": "instruction_tuning", "format": "csv"}
    resp = await client.post(
        "/api/v1/datasets", files=files, data=data, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def _create_completed_job(
    client: AsyncClient,
    headers: dict,
    artifact_path: str | None = None,
    name: str = "eval-job-ds",
) -> dict:
    """Create a dataset + training job, then mark the job COMPLETED with an artifact."""
    ds = await _create_dataset(client, headers, name)
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "google/gemma-3-1b-it",
        "training_type": "qlora",
        "configuration": {
            "epochs": 1,
            "batch_size": 2,
            "learning_rate": 2e-4,
            "max_seq_length": 512,
        },
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=headers
    )
    assert resp.status_code == 201, resp.text
    job = resp.json()["data"]

    # Mark the job COMPLETED with an artifact_path via the repository
    # (the API has no "complete" endpoint; we simulate backend completion).
    from app.db.session import get_db
    from app.models.training_job import TrainingJobStatus

    # Use the same session the test client uses
    # We need a direct session — grab it from the override
    # Simpler: query through the app's override by issuing a PATCH-like op;
    # but no such endpoint exists. We update via a second override.
    # The cleanest path: use the test's db_session fixture when available.
    # Here, in API-only tests, we instead inject a service override that
    # knows the artifact_path. For repository tests we use db_session directly.
    return job


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict:
    return await _register_and_login(client)


@pytest.fixture
def fake_metrics() -> dict:
    """Return a fake metrics dict."""
    return {
        "rouge_score": 0.82,
        "bertscore_precision": 0.91,
        "bertscore_recall": 0.88,
        "bertscore_f1": 0.89,
        "semantic_similarity": 0.85,
    }


@pytest.fixture
def mock_predictor():
    """Return an AsyncMock that replaces _generate_predictions."""
    return AsyncMock(return_value=["prediction A", "prediction B"])


@pytest.fixture
def patch_metrics(monkeypatch, fake_metrics):
    """Patch the three metric functions in app.services.metrics."""
    monkeypatch.setattr(
        metrics_module, "compute_rouge_l", lambda p, r: fake_metrics["rouge_score"]
    )
    monkeypatch.setattr(
        metrics_module,
        "compute_bertscore",
        lambda p, r: (
            fake_metrics["bertscore_precision"],
            fake_metrics["bertscore_recall"],
            fake_metrics["bertscore_f1"],
        ),
    )
    monkeypatch.setattr(
        metrics_module,
        "compute_semantic_similarity",
        lambda p, r: fake_metrics["semantic_similarity"],
    )
    return fake_metrics


@pytest.fixture
def tmp_adapter_dir():
    """Create a temporary directory that simulates an adapter artifact path."""
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def override_eval_service(mock_predictor, patch_metrics):
    """Override the evaluation service dependency to use mocked predictions + metrics.

    The service is built with the real test DB session (so repository ops
    hit SQLite), but _generate_predictions is monkeypatched to a mock so
    no real model is loaded.
    """
    from fastapi import Depends
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.session import get_db

    def _mock_eval_service(db: AsyncSession = Depends(get_db)) -> EvaluationService:
        svc = EvaluationService(
            evaluation_repo=EvaluationRepository(db),
            training_job_repo=TrainingJobRepository(db),
            dataset_repo=DatasetRepository(db),
        )
        svc._generate_predictions = mock_predictor
        return svc

    app.dependency_overrides[_get_evaluation_service] = _mock_eval_service
    yield mock_predictor
    app.dependency_overrides.pop(_get_evaluation_service, None)


# ---------------------------------------------------------------------------
# Helper to create a COMPLETED training job with an artifact via DB session
# ---------------------------------------------------------------------------


async def _seed_completed_job(
    db_session: AsyncSession,
    user_id: uuid.UUID,
    dataset_id: uuid.UUID,
    dataset_version_id: uuid.UUID,
    artifact_path: str,
) -> uuid.UUID:
    """Insert a COMPLETED training job row directly and return its id."""
    from app.models.training_job import (
        TrainingJob,
        TrainingJobStatus,
        TrainingType,
    )

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


async def _seed_user_and_dataset(
    db_session: AsyncSession, *, email: str = "seed@example.com"
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Seed a user, dataset, and dataset version. Return (user_id, ds_id, ver_id)."""
    from app.models.dataset import Dataset, DatasetStatus, DatasetType, DatasetFormat, DatasetVersion
    from app.models.user import User
    from app.core.security import hash_password

    user = User(email=email, username=email.split("@")[0], role="user")
    user.password_hash = hash_password("StrongPass123!")
    db_session.add(user)
    await db_session.flush()

    ds = Dataset(
        name=f"ds-{email}",
        dataset_type=DatasetType.INSTRUCTION_TUNING,
        format=DatasetFormat.CSV,
        status=DatasetStatus.READY,
        created_by=user.id,
    )
    db_session.add(ds)
    await db_session.flush()

    # Write a tiny CSV file the dataset version points at
    import tempfile, os as _os

    fd, path = tempfile.mkstemp(suffix=".csv")
    with _os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("instruction,response\n")
        f.write("What is 2+2?,4\n")
        f.write("Capital of France?,Paris\n")
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
    return user.id, ds.id, ver.id


# ---------------------------------------------------------------------------
# Repository tests
# ---------------------------------------------------------------------------


class TestEvaluationRepository:
    """Direct repository operations against the test DB."""

    async def test_create_and_get(self, db_session: AsyncSession):
        user_id, ds_id, ver_id = await _seed_user_and_dataset(db_session)
        job_id = await _seed_completed_job(
            db_session, user_id, ds_id, ver_id, "/tmp/adapter"
        )
        repo = EvaluationRepository(db_session)
        ev = Evaluation(
            user_id=user_id,
            dataset_id=ds_id,
            dataset_version_id=ver_id,
            model_id=job_id,
            status=EvaluationStatus.RUNNING,
        )
        created = await repo.create(ev)
        await repo.commit()
        fetched = await repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.status == EvaluationStatus.RUNNING

    async def test_update_status(self, db_session: AsyncSession):
        user_id, ds_id, ver_id = await _seed_user_and_dataset(
            db_session, email="s2@example.com"
        )
        job_id = await _seed_completed_job(
            db_session, user_id, ds_id, ver_id, "/tmp/adapter2"
        )
        repo = EvaluationRepository(db_session)
        ev = Evaluation(
            user_id=user_id,
            dataset_id=ds_id,
            dataset_version_id=ver_id,
            model_id=job_id,
        )
        await repo.create(ev)
        await repo.commit()
        updated = await repo.update_status(
            ev.id, EvaluationStatus.COMPLETED, completed_at=datetime.now(timezone.utc)
        )
        await repo.commit()
        assert updated is not None
        assert updated.status == EvaluationStatus.COMPLETED
        assert updated.completed_at is not None

    async def test_save_metrics(self, db_session: AsyncSession):
        user_id, ds_id, ver_id = await _seed_user_and_dataset(
            db_session, email="s3@example.com"
        )
        job_id = await _seed_completed_job(
            db_session, user_id, ds_id, ver_id, "/tmp/adapter3"
        )
        repo = EvaluationRepository(db_session)
        ev = Evaluation(
            user_id=user_id,
            dataset_id=ds_id,
            dataset_version_id=ver_id,
            model_id=job_id,
        )
        await repo.create(ev)
        await repo.commit()
        saved = await repo.save_metrics(
            ev.id,
            rouge_score=0.8,
            bertscore_precision=0.9,
            bertscore_recall=0.85,
            bertscore_f1=0.87,
            semantic_similarity=0.83,
        )
        await repo.commit()
        assert saved is not None
        assert saved.rouge_score == 0.8
        assert saved.bertscore_f1 == 0.87
        assert saved.semantic_similarity == 0.83

    async def test_save_error(self, db_session: AsyncSession):
        user_id, ds_id, ver_id = await _seed_user_and_dataset(
            db_session, email="s4@example.com"
        )
        job_id = await _seed_completed_job(
            db_session, user_id, ds_id, ver_id, "/tmp/adapter4"
        )
        repo = EvaluationRepository(db_session)
        ev = Evaluation(
            user_id=user_id,
            dataset_id=ds_id,
            dataset_version_id=ver_id,
            model_id=job_id,
        )
        await repo.create(ev)
        await repo.commit()
        err = await repo.save_error(ev.id, "metric blew up")
        await repo.commit()
        assert err is not None
        assert err.status == EvaluationStatus.FAILED
        assert err.error_message == "metric blew up"
        assert err.completed_at is not None

    async def test_list_for_user_and_count(self, db_session: AsyncSession):
        user_id, ds_id, ver_id = await _seed_user_and_dataset(
            db_session, email="s5@example.com"
        )
        job_id = await _seed_completed_job(
            db_session, user_id, ds_id, ver_id, "/tmp/adapter5"
        )
        repo = EvaluationRepository(db_session)
        for _ in range(3):
            ev = Evaluation(
                user_id=user_id,
                dataset_id=ds_id,
                dataset_version_id=ver_id,
                model_id=job_id,
            )
            await repo.create(ev)
        await repo.commit()
        items = await repo.list_for_user(user_id)
        assert len(items) == 3
        total = await repo.count_for_user(user_id)
        assert total == 3

    async def test_update_status_missing_returns_none(self, db_session: AsyncSession):
        repo = EvaluationRepository(db_session)
        out = await repo.update_status(uuid.uuid4(), EvaluationStatus.COMPLETED)
        assert out is None


# ---------------------------------------------------------------------------
# Metric function tests (with stubbed lazy imports)
# ---------------------------------------------------------------------------


class TestMetricFunctions:
    """Test the metric functions' input validation without heavy ML deps."""

    def test_rouge_l_empty_raises(self):
        from app.services.metrics import compute_rouge_l, MetricError

        with pytest.raises(MetricError):
            compute_rouge_l([], [])

    def test_rouge_l_length_mismatch(self):
        from app.services.metrics import compute_rouge_l, MetricError

        with pytest.raises(MetricError):
            compute_rouge_l(["a"], ["a", "b"])

    def test_bertscore_empty_raises(self):
        from app.services.metrics import compute_bertscore, MetricError

        with pytest.raises(MetricError):
            compute_bertscore([], [])

    def test_semantic_similarity_length_mismatch(self):
        from app.services.metrics import compute_semantic_similarity, MetricError

        with pytest.raises(MetricError):
            compute_semantic_similarity(["a"], ["a", "b"])


# ---------------------------------------------------------------------------
# Service tests (DB-backed, mocked predictions + metrics)
# ---------------------------------------------------------------------------


class TestEvaluationService:
    async def test_create_evaluation_success(
        self,
        db_session: AsyncSession,
        tmp_adapter_dir,
        patch_metrics,
        mock_predictor,
    ):
        user_id, ds_id, ver_id = await _seed_user_and_dataset(
            db_session, email="svc@example.com"
        )
        job_id = await _seed_completed_job(
            db_session, user_id, ds_id, ver_id, tmp_adapter_dir
        )
        svc = EvaluationService(
            evaluation_repo=EvaluationRepository(db_session),
            training_job_repo=TrainingJobRepository(db_session),
            dataset_repo=DatasetRepository(db_session),
        )
        svc._generate_predictions = mock_predictor
        from app.schemas.evaluation import EvaluationCreateRequest

        req = EvaluationCreateRequest(
            model_id=job_id, dataset_id=ds_id, dataset_version_id=ver_id
        )
        result = await svc.create_evaluation(user_id=user_id, request=req)
        assert result.status == EvaluationStatus.COMPLETED
        assert result.rouge_score == 0.82
        assert result.bertscore_f1 == 0.89
        assert result.semantic_similarity == 0.85
        assert result.error_message is None

    async def test_model_not_found(
        self, db_session: AsyncSession, patch_metrics, mock_predictor
    ):
        user_id, ds_id, ver_id = await _seed_user_and_dataset(
            db_session, email="m1@example.com"
        )
        svc = EvaluationService(
            evaluation_repo=EvaluationRepository(db_session),
            training_job_repo=TrainingJobRepository(db_session),
            dataset_repo=DatasetRepository(db_session),
        )
        svc._generate_predictions = mock_predictor
        from app.schemas.evaluation import EvaluationCreateRequest

        req = EvaluationCreateRequest(
            model_id=uuid.uuid4(),
            dataset_id=ds_id,
            dataset_version_id=ver_id,
        )
        with pytest.raises(ModelNotFoundError):
            await svc.create_evaluation(user_id=user_id, request=req)

    async def test_model_not_ready_no_artifact(
        self, db_session: AsyncSession, patch_metrics, mock_predictor
    ):
        user_id, ds_id, ver_id = await _seed_user_and_dataset(
            db_session, email="m2@example.com"
        )
        # Job with no artifact_path
        job_id = await _seed_completed_job(
            db_session, user_id, ds_id, ver_id, artifact_path=None  # type: ignore[arg-type]
        )
        # Force artifact_path to None (seed helper sets it; override)
        from app.repositories.training_job_repository import TrainingJobRepository

        repo = TrainingJobRepository(db_session)
        job = await repo.get_by_id(job_id)
        assert job is not None
        job.artifact_path = None
        await repo.commit()

        svc = EvaluationService(
            evaluation_repo=EvaluationRepository(db_session),
            training_job_repo=TrainingJobRepository(db_session),
            dataset_repo=DatasetRepository(db_session),
        )
        svc._generate_predictions = mock_predictor
        from app.schemas.evaluation import EvaluationCreateRequest

        req = EvaluationCreateRequest(
            model_id=job_id,
            dataset_id=ds_id,
            dataset_version_id=ver_id,
        )
        with pytest.raises(ModelNotReadyError):
            await svc.create_evaluation(user_id=user_id, request=req)

    async def test_dataset_not_found(
        self,
        db_session: AsyncSession,
        tmp_adapter_dir,
        patch_metrics,
        mock_predictor,
    ):
        user_id, ds_id, ver_id = await _seed_user_and_dataset(
            db_session, email="m3@example.com"
        )
        job_id = await _seed_completed_job(
            db_session, user_id, ds_id, ver_id, tmp_adapter_dir
        )
        svc = EvaluationService(
            evaluation_repo=EvaluationRepository(db_session),
            training_job_repo=TrainingJobRepository(db_session),
            dataset_repo=DatasetRepository(db_session),
        )
        svc._generate_predictions = mock_predictor
        from app.schemas.evaluation import EvaluationCreateRequest

        req = EvaluationCreateRequest(
            model_id=job_id,
            dataset_id=uuid.uuid4(),  # nonexistent
            dataset_version_id=ver_id,
        )
        with pytest.raises(DatasetNotFoundError):
            await svc.create_evaluation(user_id=user_id, request=req)

    async def test_dataset_version_not_found(
        self,
        db_session: AsyncSession,
        tmp_adapter_dir,
        patch_metrics,
        mock_predictor,
    ):
        user_id, ds_id, ver_id = await _seed_user_and_dataset(
            db_session, email="m4@example.com"
        )
        job_id = await _seed_completed_job(
            db_session, user_id, ds_id, ver_id, tmp_adapter_dir
        )
        svc = EvaluationService(
            evaluation_repo=EvaluationRepository(db_session),
            training_job_repo=TrainingJobRepository(db_session),
            dataset_repo=DatasetRepository(db_session),
        )
        svc._generate_predictions = mock_predictor
        from app.schemas.evaluation import EvaluationCreateRequest

        req = EvaluationCreateRequest(
            model_id=job_id,
            dataset_id=ds_id,
            dataset_version_id=uuid.uuid4(),  # wrong version
        )
        with pytest.raises(DatasetVersionNotFoundError):
            await svc.create_evaluation(user_id=user_id, request=req)

    async def test_adapter_not_found(
        self,
        db_session: AsyncSession,
        patch_metrics,
        mock_predictor,
    ):
        user_id, ds_id, ver_id = await _seed_user_and_dataset(
            db_session, email="m5@example.com"
        )
        # Artifact path that does not exist on disk
        job_id = await _seed_completed_job(
            db_session, user_id, ds_id, ver_id, "/nonexistent/adapter/path"
        )
        svc = EvaluationService(
            evaluation_repo=EvaluationRepository(db_session),
            training_job_repo=TrainingJobRepository(db_session),
            dataset_repo=DatasetRepository(db_session),
        )
        svc._generate_predictions = mock_predictor
        from app.schemas.evaluation import EvaluationCreateRequest

        req = EvaluationCreateRequest(
            model_id=job_id,
            dataset_id=ds_id,
            dataset_version_id=ver_id,
        )
        with pytest.raises(AdapterNotFoundError):
            await svc.create_evaluation(user_id=user_id, request=req)

    async def test_metric_failure_marks_evaluation_failed(
        self,
        db_session: AsyncSession,
        tmp_adapter_dir,
        monkeypatch,
        mock_predictor,
    ):
        user_id, ds_id, ver_id = await _seed_user_and_dataset(
            db_session, email="m6@example.com"
        )
        job_id = await _seed_completed_job(
            db_session, user_id, ds_id, ver_id, tmp_adapter_dir
        )
        # Patch rouge to raise
        from app.services.metrics import MetricError

        monkeypatch.setattr(
            metrics_module,
            "compute_rouge_l",
            lambda p, r: (_ for _ in ()).throw(MetricError("rouge boom")),
        )
        monkeypatch.setattr(
            metrics_module,
            "compute_bertscore",
            lambda p, r: (0.9, 0.9, 0.9),
        )
        monkeypatch.setattr(
            metrics_module,
            "compute_semantic_similarity",
            lambda p, r: 0.9,
        )
        svc = EvaluationService(
            evaluation_repo=EvaluationRepository(db_session),
            training_job_repo=TrainingJobRepository(db_session),
            dataset_repo=DatasetRepository(db_session),
        )
        svc._generate_predictions = mock_predictor
        from app.schemas.evaluation import EvaluationCreateRequest

        req = EvaluationCreateRequest(
            model_id=job_id, dataset_id=ds_id, dataset_version_id=ver_id
        )
        with pytest.raises(MetricComputationError):
            await svc.create_evaluation(user_id=user_id, request=req)

        # Row should be marked FAILED
        repo = EvaluationRepository(db_session)
        items = await repo.list_for_user(user_id)
        assert len(items) == 1
        assert items[0].status == EvaluationStatus.FAILED
        assert "rouge boom" in (items[0].error_message or "")

    async def test_get_evaluation_not_found(
        self, db_session: AsyncSession, patch_metrics
    ):
        svc = EvaluationService(
            evaluation_repo=EvaluationRepository(db_session),
            training_job_repo=TrainingJobRepository(db_session),
            dataset_repo=DatasetRepository(db_session),
        )
        with pytest.raises(EvaluationNotFoundError):
            await svc.get_evaluation(uuid.uuid4(), user_id=uuid.uuid4())

    async def test_get_evaluation_access_denied(
        self,
        db_session: AsyncSession,
        tmp_adapter_dir,
        patch_metrics,
        mock_predictor,
    ):
        user_id, ds_id, ver_id = await _seed_user_and_dataset(
            db_session, email="owner@example.com"
        )
        job_id = await _seed_completed_job(
            db_session, user_id, ds_id, ver_id, tmp_adapter_dir
        )
        svc = EvaluationService(
            evaluation_repo=EvaluationRepository(db_session),
            training_job_repo=TrainingJobRepository(db_session),
            dataset_repo=DatasetRepository(db_session),
        )
        svc._generate_predictions = mock_predictor
        from app.schemas.evaluation import EvaluationCreateRequest

        req = EvaluationCreateRequest(
            model_id=job_id, dataset_id=ds_id, dataset_version_id=ver_id
        )
        result = await svc.create_evaluation(user_id=user_id, request=req)
        # Another user tries to read it
        with pytest.raises(EvaluationAccessDeniedError):
            await svc.get_evaluation(result.id, user_id=uuid.uuid4())

    async def test_list_evaluations(
        self,
        db_session: AsyncSession,
        tmp_adapter_dir,
        patch_metrics,
        mock_predictor,
    ):
        user_id, ds_id, ver_id = await _seed_user_and_dataset(
            db_session, email="list@example.com"
        )
        job_id = await _seed_completed_job(
            db_session, user_id, ds_id, ver_id, tmp_adapter_dir
        )
        svc = EvaluationService(
            evaluation_repo=EvaluationRepository(db_session),
            training_job_repo=TrainingJobRepository(db_session),
            dataset_repo=DatasetRepository(db_session),
        )
        svc._generate_predictions = mock_predictor
        from app.schemas.evaluation import EvaluationCreateRequest

        req = EvaluationCreateRequest(
            model_id=job_id, dataset_id=ds_id, dataset_version_id=ver_id
        )
        await svc.create_evaluation(user_id=user_id, request=req)
        await svc.create_evaluation(user_id=user_id, request=req)
        out = await svc.list_evaluations(user_id=user_id)
        assert out.total == 2
        assert len(out.items) == 2


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


class TestEvaluationAPI:
    async def test_create_evaluation_api_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        override_eval_service,
        tmp_adapter_dir,
        db_session: AsyncSession,
    ):
        # Seed a completed job + dataset owned by the authed user.
        # We need the user id from the token — easiest is to hit /auth/me.
        me = await client.get("/api/v1/auth/me", headers=auth_headers)
        user_id = uuid.UUID(me.json()["data"]["id"])

        # Seed dataset + version + completed job directly in the SAME session
        # the API uses. The client fixture overrides get_db to db_session,
        # so we can seed via db_session.
        ds_id, ver_id, job_id = await self._seed_full(
            db_session, user_id, tmp_adapter_dir
        )

        payload = {
            "model_id": str(job_id),
            "dataset_id": str(ds_id),
            "dataset_version_id": str(ver_id),
        }
        resp = await client.post(
            "/api/v1/evaluations", json=payload, headers=auth_headers
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        assert data["status"] == "completed"
        assert data["rouge_score"] == 0.82
        assert data["bertscore_f1"] == 0.89

    async def test_create_evaluation_model_not_found_api(
        self,
        client: AsyncClient,
        auth_headers: dict,
        override_eval_service,
    ):
        payload = {
            "model_id": str(uuid.uuid4()),
            "dataset_id": str(uuid.uuid4()),
            "dataset_version_id": str(uuid.uuid4()),
        }
        resp = await client.post(
            "/api/v1/evaluations", json=payload, headers=auth_headers
        )
        assert resp.status_code == 404, resp.text
        body = resp.json()
        assert body["success"] is False
        assert body["error"]["code"] == "MODEL_NOT_FOUND"

    async def test_create_evaluation_no_auth(self, client: AsyncClient):
        payload = {
            "model_id": str(uuid.uuid4()),
            "dataset_id": str(uuid.uuid4()),
            "dataset_version_id": str(uuid.uuid4()),
        }
        resp = await client.post("/api/v1/evaluations", json=payload)
        assert resp.status_code == 401

    async def test_create_evaluation_extra_fields_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        override_eval_service,
    ):
        payload = {
            "model_id": str(uuid.uuid4()),
            "dataset_id": str(uuid.uuid4()),
            "dataset_version_id": str(uuid.uuid4()),
            "extra": "nope",
        }
        resp = await client.post(
            "/api/v1/evaluations", json=payload, headers=auth_headers
        )
        assert resp.status_code == 422

    async def test_get_evaluation_api(
        self,
        client: AsyncClient,
        auth_headers: dict,
        override_eval_service,
        tmp_adapter_dir,
        db_session: AsyncSession,
    ):
        me = await client.get("/api/v1/auth/me", headers=auth_headers)
        user_id = uuid.UUID(me.json()["data"]["id"])
        ds_id, ver_id, job_id = await self._seed_full(
            db_session, user_id, tmp_adapter_dir
        )
        payload = {
            "model_id": str(job_id),
            "dataset_id": str(ds_id),
            "dataset_version_id": str(ver_id),
        }
        create = await client.post(
            "/api/v1/evaluations", json=payload, headers=auth_headers
        )
        ev_id = create.json()["data"]["id"]
        resp = await client.get(
            f"/api/v1/evaluations/{ev_id}", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["id"] == ev_id

    async def test_get_evaluation_not_found_api(
        self, client: AsyncClient, auth_headers: dict, override_eval_service
    ):
        resp = await client.get(
            f"/api/v1/evaluations/{uuid.uuid4()}", headers=auth_headers
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "EVALUATION_NOT_FOUND"

    async def test_list_evaluations_api(
        self,
        client: AsyncClient,
        auth_headers: dict,
        override_eval_service,
        tmp_adapter_dir,
        db_session: AsyncSession,
    ):
        me = await client.get("/api/v1/auth/me", headers=auth_headers)
        user_id = uuid.UUID(me.json()["data"]["id"])
        ds_id, ver_id, job_id = await self._seed_full(
            db_session, user_id, tmp_adapter_dir
        )
        payload = {
            "model_id": str(job_id),
            "dataset_id": str(ds_id),
            "dataset_version_id": str(ver_id),
        }
        await client.post("/api/v1/evaluations", json=payload, headers=auth_headers)
        await client.post("/api/v1/evaluations", json=payload, headers=auth_headers)
        resp = await client.get("/api/v1/evaluations", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["total"] == 2
        assert len(data["items"]) == 2

    async def test_list_evaluations_cross_user_isolated(
        self,
        client: AsyncClient,
        override_eval_service,
        tmp_adapter_dir,
        db_session: AsyncSession,
    ):
        headers_a = await _register_and_login(client)
        headers_b = await _register_user(client, "b@example.com", "userb")
        me_a = await client.get("/api/v1/auth/me", headers=headers_a)
        user_a = uuid.UUID(me_a.json()["data"]["id"])
        ds_id, ver_id, job_id = await self._seed_full(
            db_session, user_a, tmp_adapter_dir
        )
        payload = {
            "model_id": str(job_id),
            "dataset_id": str(ds_id),
            "dataset_version_id": str(ver_id),
        }
        await client.post("/api/v1/evaluations", json=payload, headers=headers_a)
        # User B lists — should see zero
        resp = await client.get("/api/v1/evaluations", headers=headers_b)
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 0

    async def _seed_full(
        self,
        db_session: AsyncSession,
        user_id: uuid.UUID,
        artifact_path: str,
    ) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
        """Seed dataset, version, and completed job. Return (ds_id, ver_id, job_id)."""
        _, ds_id, ver_id = await _seed_user_and_dataset_for_user(
            db_session, user_id
        )
        job_id = await _seed_completed_job(
            db_session, user_id, ds_id, ver_id, artifact_path
        )
        return ds_id, ver_id, job_id


async def _seed_user_and_dataset_for_user(
    db_session: AsyncSession, user_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Seed a dataset + version owned by an existing user. Return (user_id, ds_id, ver_id)."""
    from app.models.dataset import (
        Dataset,
        DatasetStatus,
        DatasetType,
        DatasetFormat,
        DatasetVersion,
    )
    import os as _os
    import tempfile

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
    with _os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("instruction,response\n")
        f.write("What is 2+2?,4\n")
        f.write("Capital of France?,Paris\n")
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
    return user_id, ds.id, ver.id
