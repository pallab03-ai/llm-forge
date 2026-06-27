"""Case-insensitive uniqueness for users.email and users.username

Revision ID: 0002_unique_lower_email_username
Revises: 0001_create_users_table
Create Date: 2025-01-15 00:00:00.000000

Why this migration exists
-------------------------
The application layer normalizes ``email`` and ``username`` to lowercase before
persistence and lookup (see ``UserRepository`` and ``AuthService.register``).
However, the original migration ``0001_create_users_table`` created plain
unique indexes on the raw columns, which are case-sensitive in PostgreSQL.

That left a bypass path: a direct INSERT (admin script, future internal tool,
or a bug in a future code path that forgets to normalize) could create two
rows whose ``email`` differ only in case (``Alice@Example.com`` and
``alice@example.com``), and the database would happily accept both.

This migration closes that gap by replacing the case-sensitive unique indexes
with PostgreSQL expression indexes on ``LOWER(email)`` and ``LOWER(username)``.
The application continues to normalize values to lowercase, so the new
indexes enforce the same invariant at the database boundary as a defense in
depth.

Notes
-----
* Expression indexes are PostgreSQL-specific. SQLite (used in unit tests)
  does not support them, so the case-insensitive uniqueness tests are
  written as direct ``Settings`` / repository unit tests that exercise the
  application-layer normalization, plus a documented integration test
  pattern for PostgreSQL.
* The downgrade drops the expression indexes and recreates the original
  case-sensitive unique indexes. After downgrade, the application-layer
  normalization is the only thing preventing duplicates.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_unique_lower_email_username"
down_revision: Union[str, None] = "0001_create_users_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Replace case-sensitive unique indexes with case-insensitive ones."""
    # Drop the original case-sensitive unique indexes created in 0001.
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_username", table_name="users")

    # Create expression indexes that enforce uniqueness on the lowercased
    # values. PostgreSQL evaluates the expression at write time and rejects
    # any row that would produce a duplicate key.
    op.execute(
        "CREATE UNIQUE INDEX ix_users_email_lower ON users (LOWER(email))"
    )
    op.execute(
        "CREATE UNIQUE INDEX ix_users_username_lower ON users (LOWER(username))"
    )


def downgrade() -> None:
    """Restore the original case-sensitive unique indexes."""
    # Drop the expression indexes.
    op.execute("DROP INDEX IF EXISTS ix_users_email_lower")
    op.execute("DROP INDEX IF EXISTS ix_users_username_lower")

    # Recreate the original case-sensitive unique indexes from 0001.
    op.create_index(
        "ix_users_email",
        "users",
        ["email"],
        unique=True,
    )
    op.create_index(
        "ix_users_username",
        "users",
        ["username"],
        unique=True,
    )
