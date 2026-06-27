"""Create deployments table.

Revision ID: 0007
Revises: 0006
Create Date: 2024-02-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum
    deployment_status = sa.Enum(
        "pending",
        "deploying",
        "active",
        "failed",
        name="deployment_status",
    )
    deployment_status.create(op.get_bind(), checkfirst=True)

    # Create deployments table
    op.create_table(
        "deployments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "model_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("deployment_name", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            deployment_status,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("endpoint_name", sa.String(length=255), nullable=False),
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
            ["owner_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index(
        "ix_deployments_owner_id", "deployments", ["owner_id"], unique=False
    )
    op.create_index(
        "ix_deployments_model_version_id",
        "deployments",
        ["model_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_deployments_deployment_name",
        "deployments",
        ["deployment_name"],
        unique=False,
    )
    op.create_index(
        "ix_deployments_endpoint_name",
        "deployments",
        ["endpoint_name"],
        unique=False,
    )
    op.create_index(
        "ix_deployments_status",
        "deployments",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_deployments_status", table_name="deployments")
    op.drop_index("ix_deployments_endpoint_name", table_name="deployments")
    op.drop_index("ix_deployments_deployment_name", table_name="deployments")
    op.drop_index(
        "ix_deployments_model_version_id", table_name="deployments"
    )
    op.drop_index("ix_deployments_owner_id", table_name="deployments")

    # Drop table
    op.drop_table("deployments")

    # Drop enum
    sa.Enum(name="deployment_status").drop(op.get_bind(), checkfirst=True)
