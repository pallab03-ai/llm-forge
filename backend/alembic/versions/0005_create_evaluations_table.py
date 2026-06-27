"""Create evaluations table.

Revision ID: 0005
Revises: 0004
Create Date: 2024-02-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum
    evaluation_status = sa.Enum(
        "pending",
        "running",
        "completed",
        "failed",
        name="evaluation_status",
    )
    evaluation_status.create(op.get_bind(), checkfirst=True)

    # Create evaluations table
    op.create_table(
        "evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", evaluation_status, nullable=False, server_default="pending"),
        sa.Column("rouge_score", sa.Float(), nullable=True),
        sa.Column("bertscore_precision", sa.Float(), nullable=True),
        sa.Column("bertscore_recall", sa.Float(), nullable=True),
        sa.Column("bertscore_f1", sa.Float(), nullable=True),
        sa.Column("semantic_similarity", sa.Float(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_id"], ["training_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index("ix_evaluations_user_id", "evaluations", ["user_id"], unique=False)
    op.create_index("ix_evaluations_status", "evaluations", ["status"], unique=False)
    op.create_index("ix_evaluations_model_id", "evaluations", ["model_id"], unique=False)
    op.create_index("ix_evaluations_dataset_id", "evaluations", ["dataset_id"], unique=False)
    op.create_index("ix_evaluations_created_at", "evaluations", ["created_at"], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_evaluations_created_at", table_name="evaluations")
    op.drop_index("ix_evaluations_dataset_id", table_name="evaluations")
    op.drop_index("ix_evaluations_model_id", table_name="evaluations")
    op.drop_index("ix_evaluations_status", table_name="evaluations")
    op.drop_index("ix_evaluations_user_id", table_name="evaluations")

    # Drop table
    op.drop_table("evaluations")

    # Drop enum
    sa.Enum(name="evaluation_status").drop(op.get_bind(), checkfirst=True)
