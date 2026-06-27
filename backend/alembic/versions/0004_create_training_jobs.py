"""Create training_jobs table.

Revision ID: 0004
Revises: 0003
Create Date: 2024-01-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enums
    training_job_status = sa.Enum(
        "queued",
        "running",
        "completed",
        "failed",
        "cancelled",
        name="training_job_status",
    )
    training_job_status.create(op.get_bind(), checkfirst=True)

    training_type = sa.Enum(
        "sft",
        "lora",
        "qlora",
        "peft",
        name="training_type",
    )
    training_type.create(op.get_bind(), checkfirst=True)

    # Create training_jobs table
    op.create_table(
        "training_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", training_job_status, nullable=False, server_default="queued"),
        sa.Column("base_model", sa.String(length=255), nullable=False),
        sa.Column("training_type", training_type, nullable=False),
        sa.Column("configuration", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("artifact_path", sa.String(length=500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index("ix_training_jobs_user_id", "training_jobs", ["user_id"], unique=False)
    op.create_index("ix_training_jobs_status", "training_jobs", ["status"], unique=False)
    op.create_index("ix_training_jobs_dataset_id", "training_jobs", ["dataset_id"], unique=False)
    op.create_index("ix_training_jobs_created_at", "training_jobs", ["created_at"], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_training_jobs_created_at", table_name="training_jobs")
    op.drop_index("ix_training_jobs_dataset_id", table_name="training_jobs")
    op.drop_index("ix_training_jobs_status", table_name="training_jobs")
    op.drop_index("ix_training_jobs_user_id", table_name="training_jobs")

    # Drop table
    op.drop_table("training_jobs")

    # Drop enums
    sa.Enum(name="training_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="training_job_status").drop(op.get_bind(), checkfirst=True)