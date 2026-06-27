"""Thin Redis / RQ wrapper for training job queueing."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from redis import Redis
from rq import Queue

from app.core.config import settings

logger = logging.getLogger(__name__)


class QueueService:
    def __init__(self) -> None:
        self._queue: Queue | None = None

    @property
    def queue(self) -> Queue:
        if self._queue is None:
            self._queue = Queue(
                "training",
                connection=Redis.from_url(settings.redis_url),
            )
        return self._queue

    def enqueue(self, job_id: UUID) -> Any:
        from app.workers.qlora_training_runner import qlora_training_runner

        rq_job = self.queue.enqueue(
            qlora_training_runner,
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
        from app.workers.qlora_training_runner import qlora_training_runner

        job_id_str = str(job_id)
        cancelled = False

        for rq_job in self.queue.get_jobs():
            # RQ stores the function and args; match by first arg.
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
        return {
            "name": self.queue.name,
            "queued": len(self.queue),
            "started": len(self.queue.started_job_registry),
            "finished": len(self.queue.finished_job_registry),
            "failed": len(self.queue.failed_job_registry),
        }
