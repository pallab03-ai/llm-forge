"""Queue service using Redis / RQ (Redis Queue).

Provides a thin abstraction over RQ so the training service can
enqueue jobs, cancel queued jobs, and inspect queue status.

Per engineering guardrails:
- Phase 4.1: QLoRATrainingRunner replaces MockTrainingRunner.
- The runner is selected based on the job's training_type.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from redis import Redis
from rq import Queue

from app.core.config import settings

logger = logging.getLogger(__name__)


def get_redis_connection() -> Redis:
    """Return a Redis connection using the configured URL."""
    return Redis.from_url(settings.redis_url)


def get_training_queue() -> Queue:
    """Return the RQ training queue (lazy-initialized)."""
    connection = get_redis_connection()
    return Queue("training", connection=connection)


class QueueService:
    """Thin wrapper around RQ for training job queue operations."""

    def __init__(self) -> None:
        self._queue: Queue | None = None

    @property
    def queue(self) -> Queue:
        """Lazy-initialize the training queue on first access."""
        if self._queue is None:
            self._queue = get_training_queue()
        return self._queue

    def enqueue(self, job_id: UUID) -> Any:
        """Enqueue a training job for background execution.

        Uses QLoRATrainingRunner for QLoRA jobs, MockTrainingRunner
        for other training types (fallback).
        Returns the RQ Job object.
        """
        from app.workers.qlora_training_runner import qlora_training_runner

        runner = qlora_training_runner

        rq_job = self.queue.enqueue(
            runner,
            str(job_id),
            job_timeout="30m",
            result_ttl=3600,
        )
        logger.info(
            "Enqueued training job",
            extra={"training_job_id": str(job_id), "rq_job_id": rq_job.id},
        )
        return rq_job

    def cancel_queued_job(self, job_id: UUID) -> bool:
        """Cancel a queued RQ job.

        Searches the training queue for a job matching the given
        training_job_id and cancels it. Returns True if a job was
        found and cancelled, False otherwise.
        """
        from app.workers.qlora_training_runner import qlora_training_runner

        job_id_str = str(job_id)
        cancelled = False

        for rq_job in self.queue.get_jobs():
            # RQ stores the function and args; match by first arg
            if (
                rq_job.func is qlora_training_runner
                and len(rq_job.args) > 0
                and rq_job.args[0] == job_id_str
            ):
                rq_job.cancel()
                logger.info(
                    "Cancelled queued RQ job",
                    extra={"training_job_id": job_id_str, "rq_job_id": rq_job.id},
                )
                cancelled = True
                break

        return cancelled

    def get_queue_status(self) -> dict[str, Any]:
        """Return the current status of the training queue.

        Returns a dict with counts of queued, started, finished,
        and failed jobs.
        """
        return {
            "name": self.queue.name,
            "queued": len(self.queue),
            "started": len(self.queue.started_job_registry),
            "finished": len(self.queue.finished_job_registry),
            "failed": len(self.queue.failed_job_registry),
        }
