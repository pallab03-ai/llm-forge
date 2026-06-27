"""Create monitoring tables.

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-28 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enums
    request_status = sa.Enum(
        "success", "failure", name="request_status"
    )
    request_status.create(op.get_bind(), checkfirst=True)

    deployment_health_state = sa.Enum(
        "healthy", "degraded", "unavailable", name="deployment_health_state"
    )
    deployment_health_state.create(op.get_bind(), checkfirst=True)

    # deployment_request_logs
    op.create_table(
        "deployment_request_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "deployment_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", request_status, nullable=False),
        sa.Column("prompt_length", sa.Integer(), nullable=False),
        sa.Column("response_length", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_status_code", sa.Integer(), nullable=True),
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
            ["deployment_id"],
            ["deployments.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_deployment_request_logs_deployment_id",
        "deployment_request_logs",
        ["deployment_id"],
        unique=False,
    )
    op.create_index(
        "ix_deployment_request_logs_timestamp",
        "deployment_request_logs",
        ["timestamp"],
        unique=False,
    )
    op.create_index(
        "ix_deployment_request_logs_status",
        "deployment_request_logs",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_deployment_request_logs_deployment_timestamp",
        "deployment_request_logs",
        ["deployment_id", "timestamp"],
        unique=False,
    )

    # deployment_healths
    op.create_table(
        "deployment_healths",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "deployment_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("health", deployment_health_state, nullable=False),
        sa.Column("message", sa.String(length=255), nullable=False),
        sa.Column(
            "last_checked",
            sa.DateTime(timezone=True),
            nullable=False,
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
            ["deployment_id"],
            ["deployments.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deployment_id", name="uq_deployment_healths_deployment_id"),
    )


def downgrade() -> None:
    op.drop_table("deployment_healths")
    op.drop_index(
        "ix_deployment_request_logs_deployment_timestamp",
        table_name="deployment_request_logs",
    )
    op.drop_index(
        "ix_deployment_request_logs_status",
        table_name="deployment_request_logs",
    )
    op.drop_index(
        "ix_deployment_request_logs_timestamp",
        table_name="deployment_request_logs",
    )
    op.drop_index(
        "ix_deployment_request_logs_deployment_id",
        table_name="deployment_request_logs",
    )
    op.drop_table("deployment_request_logs")
    sa.Enum(name="deployment_health_state").drop(
        op.get_bind(), checkfirst=True
    )
    sa.Enum(name="request_status").drop(op.get_bind(), checkfirst=True)
