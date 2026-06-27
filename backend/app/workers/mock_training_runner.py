"""Mock training runner for Phase 3.

This is a **synchronous** function executed by RQ workers.
RQ workers run in a separate process and cannot use async SQLAlchemy,
so we create a sync engine / session here.

Lifecycle:
1. Load the TrainingJob row from the database.
2. Mark it as RUNNING (with started_at timestamp).
3. Simulate training with a short sleep.
4. Create a mock artifact file (JSON with job metadata).
5. Mark the job as COMPLETED (with completed_at and artifact_path).

If anything goes wrong, the job is marked as FAILED with an
error_message.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.training_job import TrainingJob, TrainingJobStatus

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sync database setup (RQ workers are synchronous)
# ---------------------------------------------------------------------------

_sync_engine = None
_SyncSessionLocal: sessionmaker | None = None


def _get_sync_session() -> Session:
    """Return a synchronous SQLAlchemy session.

    Uses ``settings.database_url_sync`` (psycopg2-style) because RQ
    workers are synchronous and cannot use asyncpg.
    """
    global _sync_engine, _SyncSessionLocal
    if _sync_engine is None:
        _sync_engine = create_engine(settings.database_url_sync)
        _SyncSessionLocal = sessionmaker(bind=_sync_engine)
    return _SyncSessionLocal()


# ---------------------------------------------------------------------------
# Mock artifact creation
# ---------------------------------------------------------------------------


def _create_mock_artifact(job: TrainingJob) -> str:
    """Create a mock artifact file and return its path.

    The artifact is a JSON file containing job metadata, stored under
    ``settings.LOCAL_STORAGE_PATH / artifacts / {job_id} / model.json``.
    """
    artifact_dir = Path(settings.LOCAL_STORAGE_PATH) / "artifacts" / str(job.id)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    artifact_path = artifact_dir / "model.json"
    artifact_data = {
        "job_id": str(job.id),
        "base_model": job.base_model,
        "training_type": job.training_type.value,
        "configuration": job.configuration,
        "status": "completed",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "mock": True,
        "message": "This is a mock artifact created by MockTrainingRunner.",
    }
    artifact_path.write_text(json.dumps(artifact_data, indent=2))
    return str(artifact_path)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def mock_training_runner(job_id: str) -> dict:
    """Execute a mock training job.

    Called by RQ with the job UUID as a string.

    Returns a dict summary for RQ result storage.
    """
    session = _get_sync_session()
    try:
        # 1. Load job
        job = session.get(TrainingJob, UUID(job_id))
        if job is None:
            raise ValueError(f"TrainingJob {job_id} not found in database")

        # 2. Mark as RUNNING
        job.status = TrainingJobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        session.flush()

        logger.info(
            "MockTrainingRunner: job %s marked RUNNING", job_id
        )

        # 3. Simulate training (short sleep)
        time.sleep(2)

        # 4. Create mock artifact
        artifact_path = _create_mock_artifact(job)

        # 5. Mark as COMPLETED
        job.status = TrainingJobStatus.COMPLETED
        job.completed_at = datetime.now(timezone.utc)
        job.artifact_path = artifact_path
        session.commit()

        logger.info(
            "MockTrainingRunner: job %s marked COMPLETED, artifact=%s",
            job_id,
            artifact_path,
        )

        return {
            "job_id": job_id,
            "status": "completed",
            "artifact_path": artifact_path,
        }

    except Exception as exc:
        session.rollback()
        logger.exception("MockTrainingRunner: job %s FAILED", job_id)

        # Attempt to mark the job as FAILED
        try:
            job = session.get(TrainingJob, UUID(job_id))
            if job is not None:
                job.status = TrainingJobStatus.FAILED
                job.error_message = str(exc)[:2000]
                job.completed_at = datetime.now(timezone.utc)
                session.commit()
        except Exception:
            logger.exception(
                "MockTrainingRunner: failed to mark job %s as FAILED", job_id
            )
            session.rollback()

        raise
    finally:
        session.close()
