"""Add partial unique index for one-active-job-per-user constraint.

Revision ID: 0005
Revises: 0004
Create Date: 2024-01-20 00:00:00.000000

This migration creates a PostgreSQL partial unique index that enforces
the "at most one active (queued or running) training job per user"
constraint at the database level, closing the TOCTOU race condition
between the application-layer count check and the INSERT.

SQLite does not support partial unique indexes (WHERE clause), so this
migration uses raw SQL via op.execute() rather than op.create_index().
In the test suite (SQLite), the application-layer check in
TrainingService.create_job() remains the enforcement mechanism.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create partial unique index: at most one active job per user.

    The index allows only one row per user_id where status is in
    ('queued', 'running'). Completed, failed, or cancelled jobs are
    excluded from the index and therefore do not block new jobs.
    """
    op.execute(
        """
        CREATE UNIQUE INDEX uq_one_active_job_per_user
        ON training_jobs (user_id)
        WHERE status IN ('queued', 'running')
        """
    )


def downgrade() -> None:
    """Remove the partial unique index."""
    op.execute(
        """
        DROP INDEX IF EXISTS uq_one_active_job_per_user
        """
    )
