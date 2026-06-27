"""create users table

Revision ID: 0001_create_users_table
Revises:
Create Date: 2025-01-01 00:00:00.000000

Phase 1: introduces the `users` table for authentication.

Columns:
- id: UUID primary key (server-side default gen_random_uuid()).
- email: VARCHAR(255), unique, indexed.
- username: VARCHAR(64), unique, indexed.
- password_hash: VARCHAR(255), bcrypt hash.
- role: enum (user | admin), default 'user'.
- created_at: TIMESTAMPTZ, server default now().
- updated_at: TIMESTAMPTZ, server default now(), refreshed on UPDATE.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_create_users_table"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create the `users` table and supporting indexes / enum."""
    # Ensure pgcrypto is available for gen_random_uuid().
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    user_role_enum = sa.Enum("user", "admin", name="user_role")
    user_role_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            sa.Enum("user", "admin", name="user_role", create_type=False),
            nullable=False,
            server_default="user",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_id", "users", ["id"], unique=False)


def downgrade() -> None:
    """Drop the `users` table and the `user_role` enum."""
    op.drop_index("ix_users_id", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
