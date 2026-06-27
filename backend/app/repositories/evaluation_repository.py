"""Evaluation repository."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evaluation import Evaluation, EvaluationStatus
from app.repositories.base import BaseRepository


class EvaluationRepository(BaseRepository[Evaluation]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=Evaluation)

    async def create(self, evaluation: Evaluation) -> Evaluation:
        return await self.add(evaluation)

    async def get_by_id(self, evaluation_id: UUID) -> Evaluation | None:
        result = await self._session.execute(
            select(Evaluation).where(Evaluation.id == evaluation_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Evaluation]:
        stmt = (
            select(Evaluation)
            .where(Evaluation.user_id == user_id)
            .order_by(Evaluation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_user(self, user_id: UUID) -> int:
        stmt = select(func.count(Evaluation.id)).where(
            Evaluation.user_id == user_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0

    async def update_status(
        self,
        evaluation_id: UUID,
        status: EvaluationStatus,
        *,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> Evaluation | None:
        ev = await self.get_by_id(evaluation_id)
        if ev is None:
            return None
        ev.status = status
        if started_at is not None:
            ev.started_at = started_at
        if completed_at is not None:
            ev.completed_at = completed_at
        await self._session.flush()
        await self._session.refresh(ev)
        return ev

    async def save_metrics(
        self,
        evaluation_id: UUID,
        *,
        rouge_score: float | None,
        bertscore_precision: float | None,
        bertscore_recall: float | None,
        bertscore_f1: float | None,
        semantic_similarity: float | None,
    ) -> Evaluation | None:
        ev = await self.get_by_id(evaluation_id)
        if ev is None:
            return None
        ev.rouge_score = rouge_score
        ev.bertscore_precision = bertscore_precision
        ev.bertscore_recall = bertscore_recall
        ev.bertscore_f1 = bertscore_f1
        ev.semantic_similarity = semantic_similarity
        await self._session.flush()
        await self._session.refresh(ev)
        return ev

    async def save_error(
        self, evaluation_id: UUID, error_message: str
    ) -> Evaluation | None:
        ev = await self.get_by_id(evaluation_id)
        if ev is None:
            return None
        ev.status = EvaluationStatus.FAILED
        ev.error_message = error_message
        ev.completed_at = datetime.now(timezone.utc)
        await self._session.flush()
        await self._session.refresh(ev)
        return ev
