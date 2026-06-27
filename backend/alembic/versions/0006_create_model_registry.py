"""Create model registry tables.

Revision ID: 0006
Revises: 0005
Create Date: 2024-02-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum
    model_version_status = sa.Enum(
        "draft",
        "staging",
        "production",
        "archived",
        name="model_version_status",
    )
    model_version_status.create(op.get_bind(), checkfirst=True)

    # Create models table
    op.create_table(
        "models",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create model_versions table
    op.create_table(
        "model_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "training_job_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column(
            "evaluation_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("artifact_path", sa.String(length=1024), nullable=False),
        sa.Column("metrics_snapshot", sa.JSON(), nullable=True),
        sa.Column(
            "status",
            model_version_status,
            nullable=False,
            server_default="staging",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["model_id"], ["models.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["training_job_id"], ["training_jobs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id"], ["evaluations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index("ix_models_owner_id", "models", ["owner_id"], unique=False)
    op.create_index(
        "ix_model_versions_model_id",
        "model_versions",
        ["model_id"],
        unique=False,
    )
    op.create_index(
        "ix_model_versions_training_job_id",
        "model_versions",
        ["training_job_id"],
        unique=False,
    )
    op.create_index(
        "ix_model_versions_evaluation_id",
        "model_versions",
        ["evaluation_id"],
        unique=False,
    )
    op.create_index(
        "ix_model_versions_status",
        "model_versions",
        ["status"],
        unique=False,
    )

    # Unique constraint: one version number per model
    op.create_unique_constraint(
        "uq_model_versions_model_id_version_number",
        "model_versions",
        ["model_id", "version_number"],
    )


def downgrade() -> None:
    # Drop unique constraint
    op.drop_constraint(
        "uq_model_versions_model_id_version_number",
        "model_versions",
        type_="unique",
    )

    # Drop indexes
    op.drop_index("ix_model_versions_status", table_name="model_versions")
    op.drop_index(
        "ix_model_versions_evaluation_id", table_name="model_versions"
    )
    op.drop_index(
        "ix_model_versions_training_job_id", table_name="model_versions"
    )
    op.drop_index("ix_model_versions_model_id", table_name="model_versions")
    op.drop_index("ix_models_owner_id", table_name="models")

    # Drop tables
    op.drop_table("model_versions")
    op.drop_table("models")

    # Drop enum
    sa.Enum(name="model_version_status").drop(op.get_bind(), checkfirst=True)
