"""Tests for the Training Job API.

Covers:
- Create training job (success, dataset not owned, active job limit)
- Get training job (success, not found, access denied)
- List training jobs (success, pagination, empty list)
- Cancel training job (success for QUEUED/RUNNING, not cancellable)
- Schema validation (extra fields forbidden, TrainingConfig bounds)
- Cross-user access (cannot view/cancel other user's jobs)
- Auth required (missing token)
- Active job limit enforcement (QUEUED blocks new, RUNNING blocks new,
  COMPLETED allows new)
"""

from __future__ import annotations

import io
import json
import uuid

import pytest
from httpx import AsyncClient
from unittest.mock import MagicMock

from app.api.v1.training_jobs import _get_training_service
from app.main import app
from app.services.queue_service import QueueService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _csv_bytes(rows: list[dict]) -> bytes:
    """Build CSV bytes from a list of dicts."""
    if not rows:
        return b""
    headers = list(rows[0].keys())
    lines = [",".join(headers)]
    for row in rows:
        lines.append(",".join(str(row.get(h, "")) for h in headers))
    return ("\n".join(lines) + "\n").encode("utf-8")


async def _register_and_login(client: AsyncClient) -> dict:
    """Register a user and return auth headers."""
    payload = {
        "email": "trainer@example.com",
        "username": "trainer",
        "password": "StrongPass123!",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    token = data["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _register_user(
    client: AsyncClient, email: str, username: str
) -> dict:
    """Register a new user and return auth headers."""
    payload = {
        "email": email,
        "username": username,
        "password": "StrongPass123!",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _create_dataset(
    client: AsyncClient, headers: dict, name: str = "test-ds"
) -> dict:
    """Create a dataset via the API and return the data dict."""
    rows = [{"instruction": "Q", "response": "A"}]
    files = {"file": ("a.csv", _csv_bytes(rows), "text/csv")}
    data = {
        "name": name,
        "dataset_type": "instruction_tuning",
        "format": "csv",
    }
    resp = await client.post(
        "/api/v1/datasets", files=files, data=data, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _default_config() -> dict:
    """Return a valid training configuration dict."""
    return {
        "epochs": 3,
        "batch_size": 8,
        "learning_rate": 0.0001,
        "max_seq_length": 2048,
    }


async def _create_training_job(
    client: AsyncClient,
    headers: dict,
    dataset_id: str | None = None,
    dataset_version_id: str | None = None,
    base_model: str = "meta-llama/Llama-3.1-8B",
    training_type: str = "sft",
    configuration: dict | None = None,
) -> dict:
    """Create a training job via the API and return the data dict.

    If dataset_id / dataset_version_id are not provided, a dataset is
    created automatically using the given auth headers.
    """
    if dataset_id is None or dataset_version_id is None:
        ds = await _create_dataset(client, headers)
        dataset_id = ds["id"]
        dataset_version_id = ds["versions"][0]["id"]

    payload = {
        "dataset_id": dataset_id,
        "dataset_version_id": dataset_version_id,
        "base_model": base_model,
        "training_type": training_type,
        "configuration": configuration or _default_config(),
    }
    resp = await client.post(
        "/api/v1/training-jobs",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict:
    return await _register_and_login(client)


@pytest.fixture
def mock_queue_service() -> MagicMock:
    """Return a mock QueueService that avoids Redis connections."""
    m = MagicMock(spec=QueueService)
    m.enqueue.return_value = MagicMock(id="mock-rq-job-id")
    m.cancel_queued_job.return_value = True
    m.get_queue_status.return_value = {
        "name": "training",
        "queued": 0,
        "started": 0,
        "finished": 0,
        "failed": 0,
    }
    return m


@pytest.fixture
def override_queue(mock_queue_service: MagicMock):
    """Override the _get_training_service dependency to inject mock QueueService.

    This replaces the real QueueService (which needs Redis) with a mock,
    while still using the test DB session for repositories.
    """
    from fastapi import Depends
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.session import get_db
    from app.repositories.dataset_repository import DatasetRepository
    from app.repositories.training_job_repository import TrainingJobRepository
    from app.services.training_service import TrainingService

    def _mock_training_service(
        db: AsyncSession = Depends(get_db),
    ) -> TrainingService:
        return TrainingService(
            job_repo=TrainingJobRepository(db),
            dataset_repo=DatasetRepository(db),
            queue_service=mock_queue_service,
        )

    app.dependency_overrides[_get_training_service] = _mock_training_service
    yield mock_queue_service
    # Clean up — remove only our override
    app.dependency_overrides.pop(_get_training_service, None)


# ---------------------------------------------------------------------------
# Create training job — success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_training_job_success(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    ds = await _create_dataset(client, auth_headers, "job-create-ds")
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
        "configuration": _default_config(),
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["status"] == "queued"
    assert data["base_model"] == "meta-llama/Llama-3.1-8B"
    assert data["training_type"] == "sft"
    assert data["configuration"]["epochs"] == 3
    assert data["configuration"]["batch_size"] == 8
    assert data["artifact_path"] is None
    assert data["started_at"] is None
    assert data["completed_at"] is None
    assert data["error_message"] is None
    # QueueService.enqueue should have been called
    override_queue.enqueue.assert_called_once()


@pytest.mark.asyncio
async def test_create_training_job_lora_type(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    ds = await _create_dataset(client, auth_headers, "lora-ds")
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-2-7b",
        "training_type": "lora",
        "configuration": _default_config(),
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["training_type"] == "lora"


@pytest.mark.asyncio
async def test_create_training_job_qlora_type(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    ds = await _create_dataset(client, auth_headers, "qlora-ds")
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-2-7b",
        "training_type": "qlora",
        "configuration": _default_config(),
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["training_type"] == "qlora"


@pytest.mark.asyncio
async def test_create_training_job_peft_type(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    ds = await _create_dataset(client, auth_headers, "peft-ds")
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-2-7b",
        "training_type": "peft",
        "configuration": _default_config(),
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["training_type"] == "peft"


# ---------------------------------------------------------------------------
# Create training job — dataset not owned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_job_dataset_not_owned(
    client: AsyncClient, override_queue: MagicMock
):
    """User B cannot create a training job using User A's dataset."""
    owner_headers = await _register_user(
        client, "owner-ds@example.com", "owner-ds"
    )
    other_headers = await _register_user(
        client, "other-ds@example.com", "other-ds"
    )

    ds = await _create_dataset(client, owner_headers, "private-ds")
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
        "configuration": _default_config(),
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=other_headers
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "DATASET_NOT_OWNED"


# ---------------------------------------------------------------------------
# Create training job — active job limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_job_active_limit_queued(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    """User with a QUEUED job cannot create another."""
    await _create_training_job(client, auth_headers)

    ds2 = await _create_dataset(client, auth_headers, "second-ds")
    payload = {
        "dataset_id": ds2["id"],
        "dataset_version_id": ds2["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
        "configuration": _default_config(),
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "ACTIVE_JOB_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_create_job_after_cancel_allows_new(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    """After cancelling a QUEUED job, user can create a new one."""
    job = await _create_training_job(client, auth_headers)

    # Cancel the job
    resp = await client.post(
        f"/api/v1/training-jobs/{job['id']}/cancel", headers=auth_headers
    )
    assert resp.status_code == 200

    # Now create a new job — should succeed
    ds2 = await _create_dataset(client, auth_headers, "post-cancel-ds")
    payload = {
        "dataset_id": ds2["id"],
        "dataset_version_id": ds2["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "lora",
        "configuration": _default_config(),
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_create_job_after_completed_allows_new(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock, db_session
):
    """After a job is COMPLETED, user can create a new one."""
    from app.models.training_job import TrainingJob, TrainingJobStatus
    from app.repositories.training_job_repository import TrainingJobRepository

    job = await _create_training_job(client, auth_headers)

    # Manually mark the job as COMPLETED (bypassing the mock runner)
    from datetime import datetime, timezone

    repo = TrainingJobRepository(db_session)
    await repo.update_status(
        uuid.UUID(job["id"]),
        TrainingJobStatus.COMPLETED,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    await repo.commit()

    # Now create a new job — should succeed
    ds2 = await _create_dataset(client, auth_headers, "post-complete-ds")
    payload = {
        "dataset_id": ds2["id"],
        "dataset_version_id": ds2["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
        "configuration": _default_config(),
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Get training job — success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_training_job_success(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    job = await _create_training_job(client, auth_headers)
    job_id = job["id"]

    resp = await client.get(
        f"/api/v1/training-jobs/{job_id}", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["id"] == job_id
    assert body["data"]["status"] == "queued"
    assert body["data"]["base_model"] == "meta-llama/Llama-3.1-8B"


# ---------------------------------------------------------------------------
# Get training job — not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_training_job_not_found(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    fake_id = str(uuid.uuid4())
    resp = await client.get(
        f"/api/v1/training-jobs/{fake_id}", headers=auth_headers
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "TRAINING_JOB_NOT_FOUND"


# ---------------------------------------------------------------------------
# Get training job — access denied (cross-user)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_training_job_access_denied(
    client: AsyncClient, override_queue: MagicMock
):
    """User B cannot view User A's training job."""
    owner_headers = await _register_user(
        client, "owner-get@example.com", "owner-get"
    )
    other_headers = await _register_user(
        client, "other-get@example.com", "other-get"
    )

    job = await _create_training_job(client, owner_headers)

    resp = await client.get(
        f"/api/v1/training-jobs/{job['id']}", headers=other_headers
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "TRAINING_JOB_ACCESS_DENIED"


# ---------------------------------------------------------------------------
# List training jobs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_training_jobs_empty(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    resp = await client.get(
        "/api/v1/training-jobs", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["items"] == []
    assert body["data"]["total"] == 0


@pytest.mark.asyncio
async def test_list_training_jobs_with_items(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    # Create two jobs (need two datasets since each job needs a dataset)
    job1 = await _create_training_job(client, auth_headers)

    # Cancel first so we can create second
    await client.post(
        f"/api/v1/training-jobs/{job1['id']}/cancel", headers=auth_headers
    )

    ds2 = await _create_dataset(client, auth_headers, "list-ds-2")
    payload2 = {
        "dataset_id": ds2["id"],
        "dataset_version_id": ds2["versions"][0]["id"],
        "base_model": "meta-llama/Llama-2-7b",
        "training_type": "lora",
        "configuration": _default_config(),
    }
    await client.post(
        "/api/v1/training-jobs", json=payload2, headers=auth_headers
    )

    resp = await client.get(
        "/api/v1/training-jobs", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["total"] == 2
    assert len(body["data"]["items"]) == 2


@pytest.mark.asyncio
async def test_list_training_jobs_pagination(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    # Create and cancel jobs to build up a list
    for i in range(3):
        ds = await _create_dataset(client, auth_headers, f"pag-ds-{i}")
        payload = {
            "dataset_id": ds["id"],
            "dataset_version_id": ds["versions"][0]["id"],
            "base_model": "meta-llama/Llama-3.1-8B",
            "training_type": "sft",
            "configuration": _default_config(),
        }
        resp = await client.post(
            "/api/v1/training-jobs", json=payload, headers=auth_headers
        )
        assert resp.status_code == 201
        job = resp.json()["data"]
        await client.post(
            f"/api/v1/training-jobs/{job['id']}/cancel", headers=auth_headers
        )

    # Request limit=1, offset=0
    resp = await client.get(
        "/api/v1/training-jobs?limit=1&offset=0", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["total"] == 3
    assert len(body["data"]["items"]) == 1
    assert body["data"]["limit"] == 1
    assert body["data"]["offset"] == 0


@pytest.mark.asyncio
async def test_list_training_jobs_offset(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    # Create and cancel 2 jobs
    job1 = await _create_training_job(client, auth_headers)
    await client.post(
        f"/api/v1/training-jobs/{job1['id']}/cancel", headers=auth_headers
    )
    ds2 = await _create_dataset(client, auth_headers, "offset-ds-2")
    payload2 = {
        "dataset_id": ds2["id"],
        "dataset_version_id": ds2["versions"][0]["id"],
        "base_model": "meta-llama/Llama-2-7b",
        "training_type": "lora",
        "configuration": _default_config(),
    }
    await client.post(
        "/api/v1/training-jobs", json=payload2, headers=auth_headers
    )

    # offset=1 should skip the first (most recent) job
    resp = await client.get(
        "/api/v1/training-jobs?limit=10&offset=1", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["total"] == 2
    assert len(body["data"]["items"]) == 1


@pytest.mark.asyncio
async def test_list_jobs_only_shows_own_jobs(
    client: AsyncClient, override_queue: MagicMock
):
    """User A's list should not include User B's jobs."""
    a_headers = await _register_user(client, "user-a@example.com", "user-a")
    b_headers = await _register_user(client, "user-b@example.com", "user-b")

    # User B creates a job
    await _create_training_job(client, b_headers)

    # User A's list should be empty
    resp = await client.get(
        "/api/v1/training-jobs", headers=a_headers
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 0
    assert resp.json()["data"]["items"] == []


# ---------------------------------------------------------------------------
# Cancel training job — success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_queued_job_success(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    job = await _create_training_job(client, auth_headers)

    resp = await client.post(
        f"/api/v1/training-jobs/{job['id']}/cancel", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["status"] == "cancelled"
    assert body["data"]["completed_at"] is not None
    # QueueService.cancel_queued_job should have been called for QUEUED job
    override_queue.cancel_queued_job.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_running_job_success(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock, db_session
):
    """Cancelling a RUNNING job should succeed (no RQ cancel needed)."""
    from app.models.training_job import TrainingJobStatus
    from app.repositories.training_job_repository import TrainingJobRepository
    from datetime import datetime, timezone

    job = await _create_training_job(client, auth_headers)

    # Manually mark the job as RUNNING
    repo = TrainingJobRepository(db_session)
    await repo.update_status(
        uuid.UUID(job["id"]),
        TrainingJobStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
    )
    await repo.commit()

    resp = await client.post(
        f"/api/v1/training-jobs/{job['id']}/cancel", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "cancelled"
    # cancel_queued_job should NOT have been called for RUNNING job
    override_queue.cancel_queued_job.assert_not_called()


# ---------------------------------------------------------------------------
# Cancel training job — not cancellable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_completed_job_not_cancellable(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock, db_session
):
    from app.models.training_job import TrainingJobStatus
    from app.repositories.training_job_repository import TrainingJobRepository
    from datetime import datetime, timezone

    job = await _create_training_job(client, auth_headers)

    # Mark as COMPLETED
    repo = TrainingJobRepository(db_session)
    await repo.update_status(
        uuid.UUID(job["id"]),
        TrainingJobStatus.COMPLETED,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    await repo.commit()

    resp = await client.post(
        f"/api/v1/training-jobs/{job['id']}/cancel", headers=auth_headers
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "TRAINING_JOB_NOT_CANCELLABLE"


@pytest.mark.asyncio
async def test_cancel_failed_job_not_cancellable(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock, db_session
):
    from app.models.training_job import TrainingJobStatus
    from app.repositories.training_job_repository import TrainingJobRepository

    job = await _create_training_job(client, auth_headers)

    # Mark as FAILED
    repo = TrainingJobRepository(db_session)
    await repo.update_status(
        uuid.UUID(job["id"]), TrainingJobStatus.FAILED
    )
    await repo.commit()

    resp = await client.post(
        f"/api/v1/training-jobs/{job['id']}/cancel", headers=auth_headers
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "TRAINING_JOB_NOT_CANCELLABLE"


@pytest.mark.asyncio
async def test_cancel_already_cancelled_job_not_cancellable(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    job = await _create_training_job(client, auth_headers)

    # Cancel once
    resp1 = await client.post(
        f"/api/v1/training-jobs/{job['id']}/cancel", headers=auth_headers
    )
    assert resp1.status_code == 200

    # Try to cancel again
    resp2 = await client.post(
        f"/api/v1/training-jobs/{job['id']}/cancel", headers=auth_headers
    )
    assert resp2.status_code == 409
    assert resp2.json()["error"]["code"] == "TRAINING_JOB_NOT_CANCELLABLE"


# ---------------------------------------------------------------------------
# Cancel training job — not found / access denied
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_job_not_found(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    fake_id = str(uuid.uuid4())
    resp = await client.post(
        f"/api/v1/training-jobs/{fake_id}/cancel", headers=auth_headers
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "TRAINING_JOB_NOT_FOUND"


@pytest.mark.asyncio
async def test_cancel_job_access_denied(
    client: AsyncClient, override_queue: MagicMock
):
    """User B cannot cancel User A's training job."""
    owner_headers = await _register_user(
        client, "owner-cancel@example.com", "owner-cancel"
    )
    other_headers = await _register_user(
        client, "other-cancel@example.com", "other-cancel"
    )

    job = await _create_training_job(client, owner_headers)

    resp = await client.post(
        f"/api/v1/training-jobs/{job['id']}/cancel", headers=other_headers
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "TRAINING_JOB_ACCESS_DENIED"


# ---------------------------------------------------------------------------
# Auth required
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_job_requires_auth(client: AsyncClient, override_queue: MagicMock):
    payload = {
        "dataset_id": str(uuid.uuid4()),
        "dataset_version_id": str(uuid.uuid4()),
        "base_model": "test-model",
        "training_type": "sft",
        "configuration": _default_config(),
    }
    resp = await client.post("/api/v1/training-jobs", json=payload)
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_get_job_requires_auth(client: AsyncClient, override_queue: MagicMock):
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/training-jobs/{fake_id}")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_list_jobs_requires_auth(client: AsyncClient, override_queue: MagicMock):
    resp = await client.get("/api/v1/training-jobs")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_cancel_job_requires_auth(client: AsyncClient, override_queue: MagicMock):
    fake_id = str(uuid.uuid4())
    resp = await client.post(f"/api/v1/training-jobs/{fake_id}/cancel")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Schema validation — TrainingJobCreateRequest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_job_extra_field_rejected(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    ds = await _create_dataset(client, auth_headers, "extra-field-ds")
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
        "configuration": _default_config(),
        "unexpected_field": "should_fail",
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_job_missing_dataset_id(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    payload = {
        "dataset_version_id": str(uuid.uuid4()),
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
        "configuration": _default_config(),
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_job_missing_base_model(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    ds = await _create_dataset(client, auth_headers, "no-model-ds")
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "training_type": "sft",
        "configuration": _default_config(),
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_job_missing_training_type(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    ds = await _create_dataset(client, auth_headers, "no-type-ds")
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "configuration": _default_config(),
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_job_missing_configuration(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    ds = await _create_dataset(client, auth_headers, "no-config-ds")
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_job_invalid_training_type(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    ds = await _create_dataset(client, auth_headers, "bad-type-ds")
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "invalid_type",
        "configuration": _default_config(),
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_job_empty_base_model(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    ds = await _create_dataset(client, auth_headers, "empty-model-ds")
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "",
        "training_type": "sft",
        "configuration": _default_config(),
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Schema validation — TrainingConfig bounds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_config_extra_field_rejected(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    ds = await _create_dataset(client, auth_headers, "config-extra-ds")
    config = _default_config()
    config["extra_param"] = True
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
        "configuration": config,
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_config_epochs_below_minimum(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    ds = await _create_dataset(client, auth_headers, "epochs-min-ds")
    config = _default_config()
    config["epochs"] = 0
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
        "configuration": config,
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_config_epochs_above_maximum(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    ds = await _create_dataset(client, auth_headers, "epochs-max-ds")
    config = _default_config()
    config["epochs"] = 11
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
        "configuration": config,
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_config_batch_size_below_minimum(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    ds = await _create_dataset(client, auth_headers, "bs-min-ds")
    config = _default_config()
    config["batch_size"] = 0
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
        "configuration": config,
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_config_batch_size_above_maximum(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    ds = await _create_dataset(client, auth_headers, "bs-max-ds")
    config = _default_config()
    config["batch_size"] = 65
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
        "configuration": config,
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_config_learning_rate_below_minimum(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    ds = await _create_dataset(client, auth_headers, "lr-min-ds")
    config = _default_config()
    config["learning_rate"] = 1e-8
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
        "configuration": config,
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_config_learning_rate_above_maximum(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    ds = await _create_dataset(client, auth_headers, "lr-max-ds")
    config = _default_config()
    config["learning_rate"] = 1.1
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
        "configuration": config,
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_config_max_seq_length_below_minimum(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    ds = await _create_dataset(client, auth_headers, "seq-min-ds")
    config = _default_config()
    config["max_seq_length"] = 63
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
        "configuration": config,
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_config_max_seq_length_above_maximum(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    ds = await _create_dataset(client, auth_headers, "seq-max-ds")
    config = _default_config()
    config["max_seq_length"] = 8193
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
        "configuration": config,
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_config_epochs_at_boundary_min(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    """epochs=1 (minimum) should be accepted."""
    ds = await _create_dataset(client, auth_headers, "epoch-bound-ds")
    config = _default_config()
    config["epochs"] = 1
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
        "configuration": config,
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_config_epochs_at_boundary_max(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    """epochs=10 (maximum) should be accepted."""
    ds = await _create_dataset(client, auth_headers, "epoch-max-bound-ds")
    config = _default_config()
    config["epochs"] = 10
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
        "configuration": config,
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_config_batch_size_at_boundary_max(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    """batch_size=64 (maximum) should be accepted."""
    ds = await _create_dataset(client, auth_headers, "bs-bound-ds")
    config = _default_config()
    config["batch_size"] = 64
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
        "configuration": config,
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_config_max_seq_length_at_boundary_max(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    """max_seq_length=8192 (maximum) should be accepted."""
    ds = await _create_dataset(client, auth_headers, "seq-bound-ds")
    config = _default_config()
    config["max_seq_length"] = 8192
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
        "configuration": config,
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Cross-field OOM validation (batch_size * max_seq_length > 262144)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_config_oom_rejected_batch_times_seq(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    """batch_size=64, max_seq_length=4097 → 262208 > 262144 → 422."""
    ds = await _create_dataset(client, auth_headers, "oom-ds-1")
    config = _default_config()
    config["batch_size"] = 64
    config["max_seq_length"] = 4097
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
        "configuration": config,
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_config_oom_boundary_exact_limit_batch(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    """batch_size=64, max_seq_length=4096 → 262144 == limit → 201."""
    ds = await _create_dataset(client, auth_headers, "oom-bound-ds-1")
    config = _default_config()
    config["batch_size"] = 64
    config["max_seq_length"] = 4096
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
        "configuration": config,
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_config_oom_boundary_exact_limit_seq(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    """batch_size=32, max_seq_length=8192 → 262144 == limit → 201."""
    ds = await _create_dataset(client, auth_headers, "oom-bound-ds-2")
    config = _default_config()
    config["batch_size"] = 32
    config["max_seq_length"] = 8192
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
        "configuration": config,
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_config_oom_rejected_seq_times_batch(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    """batch_size=33, max_seq_length=8192 → 270336 > 262144 → 422."""
    ds = await _create_dataset(client, auth_headers, "oom-ds-2")
    config = _default_config()
    config["batch_size"] = 33
    config["max_seq_length"] = 8192
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
        "configuration": config,
    }
    resp = await client.post(
        "/api/v1/training-jobs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Race condition — IntegrityError catch path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_job_integrity_error_returns_409(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    """When DB partial-unique-index raises IntegrityError, service returns 409."""
    from unittest.mock import AsyncMock, patch
    from sqlalchemy.exc import IntegrityError

    ds = await _create_dataset(client, auth_headers, "race-ds")
    config = _default_config()
    payload = {
        "dataset_id": ds["id"],
        "dataset_version_id": ds["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
        "configuration": config,
    }

    with patch(
        "app.services.training_service.TrainingJobRepository.commit",
        new_callable=AsyncMock,
        side_effect=IntegrityError(
            "INSERT", {}, orig=Exception("unique constraint")
        ),
    ):
        resp = await client.post(
            "/api/v1/training-jobs", json=payload, headers=auth_headers
        )
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Response shape verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_job_response_has_all_fields(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    """Verify the response includes all TrainingJobResponse fields."""
    job = await _create_training_job(client, auth_headers)
    expected_keys = {
        "id",
        "user_id",
        "dataset_id",
        "dataset_version_id",
        "status",
        "base_model",
        "training_type",
        "configuration",
        "artifact_path",
        "started_at",
        "completed_at",
        "error_message",
        "created_at",
        "updated_at",
    }
    assert set(job.keys()) == expected_keys


@pytest.mark.asyncio
async def test_list_jobs_response_has_pagination_fields(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    resp = await client.get(
        "/api/v1/training-jobs", headers=auth_headers
    )
    body = resp.json()["data"]
    assert "items" in body
    assert "total" in body
    assert "limit" in body
    assert "offset" in body


# ---------------------------------------------------------------------------
# Invalid UUID format
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_job_invalid_uuid_format(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    resp = await client.get(
        "/api/v1/training-jobs/not-a-uuid", headers=auth_headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_cancel_job_invalid_uuid_format(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock
):
    resp = await client.post(
        "/api/v1/training-jobs/not-a-uuid/cancel", headers=auth_headers
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Multiple users — isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_b_cannot_see_user_a_job_in_list(
    client: AsyncClient, override_queue: MagicMock
):
    """User A creates a job; User B's list should be empty."""
    a_headers = await _register_user(client, "isol-a@example.com", "isol-a")
    b_headers = await _register_user(client, "isol-b@example.com", "isol-b")

    await _create_training_job(client, a_headers)

    resp = await client.get(
        "/api/v1/training-jobs", headers=b_headers
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_active_job_limit_per_user(
    client: AsyncClient, override_queue: MagicMock
):
    """User A's active job should not block User B from creating one."""
    a_headers = await _register_user(client, "limit-a@example.com", "limit-a")
    b_headers = await _register_user(client, "limit-b@example.com", "limit-b")

    # User A creates a job
    ds_a = await _create_dataset(client, a_headers, "limit-ds-a")
    payload_a = {
        "dataset_id": ds_a["id"],
        "dataset_version_id": ds_a["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
        "configuration": _default_config(),
    }
    resp_a = await client.post(
        "/api/v1/training-jobs", json=payload_a, headers=a_headers
    )
    assert resp_a.status_code == 201

    # User B should still be able to create a job
    ds_b = await _create_dataset(client, b_headers, "limit-ds-b")
    payload_b = {
        "dataset_id": ds_b["id"],
        "dataset_version_id": ds_b["versions"][0]["id"],
        "base_model": "meta-llama/Llama-3.1-8B",
        "training_type": "sft",
        "configuration": _default_config(),
    }
    resp_b = await client.post(
        "/api/v1/training-jobs", json=payload_b, headers=b_headers
    )
    assert resp_b.status_code == 201
    assert resp_b.json()["data"]["status"] == "queued"


# ---------------------------------------------------------------------------
# Job status transitions via repository (unit-level)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repository_update_status(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock, db_session
):
    from app.models.training_job import TrainingJobStatus
    from app.repositories.training_job_repository import TrainingJobRepository
    from datetime import datetime, timezone

    job = await _create_training_job(client, auth_headers)
    repo = TrainingJobRepository(db_session)

    updated = await repo.update_status(
        uuid.UUID(job["id"]),
        TrainingJobStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
    )
    await repo.commit()
    assert updated is not None
    assert updated.status == TrainingJobStatus.RUNNING
    assert updated.started_at is not None


@pytest.mark.asyncio
async def test_repository_count_active_jobs(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock, db_session
):
    from app.repositories.training_job_repository import TrainingJobRepository

    repo = TrainingJobRepository(db_session)

    # Before creating any jobs
    user_id = uuid.UUID((await _register_and_login(client))["Authorization"].split(" ")[1] if False else "00000000-0000-0000-0000-000000000000")
    # Use the auth_headers user — get user_id from a created job
    job = await _create_training_job(client, auth_headers)
    user_id = uuid.UUID(job["user_id"])

    count = await repo.count_active_jobs(user_id)
    assert count == 1


@pytest.mark.asyncio
async def test_repository_count_for_user(
    client: AsyncClient, auth_headers: dict, override_queue: MagicMock, db_session
):
    from app.repositories.training_job_repository import TrainingJobRepository

    repo = TrainingJobRepository(db_session)
    job = await _create_training_job(client, auth_headers)
    user_id = uuid.UUID(job["user_id"])

    count = await repo.count_for_user(user_id)
    assert count == 1


@pytest.mark.asyncio
async def test_repository_get_by_id_not_found(db_session):
    from app.repositories.training_job_repository import TrainingJobRepository

    repo = TrainingJobRepository(db_session)
    result = await repo.get_by_id(uuid.uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_repository_update_status_not_found(db_session):
    from app.models.training_job import TrainingJobStatus
    from app.repositories.training_job_repository import TrainingJobRepository

    repo = TrainingJobRepository(db_session)
    result = await repo.update_status(uuid.uuid4(), TrainingJobStatus.RUNNING)
    assert result is None
