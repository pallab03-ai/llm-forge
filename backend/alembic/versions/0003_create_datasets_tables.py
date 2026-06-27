"""create datasets tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-19

Adds:
- datasets table
- dataset_versions table
- enums: dataset_type, dataset_format, dataset_status
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enums
    dataset_type_enum = sa.Enum(
        "instruction_tuning",
        "chat",
        "qa",
        name="dataset_type",
    )
    dataset_format_enum = sa.Enum(
        "csv",
        "json",
        "jsonl",
        name="dataset_format",
    )
    dataset_status_enum = sa.Enum(
        "uploading",
        "validating",
        "ready",
        "failed",
        "deleted",
        name="dataset_status",
    )

    dataset_type_enum.create(op.get_bind(), checkfirst=True)
    dataset_format_enum.create(op.get_bind(), checkfirst=True)
    dataset_status_enum.create(op.get_bind(), checkfirst=True)

    # datasets table
    op.create_table(
        "datasets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "dataset_type",
            sa.Enum(
                "instruction_tuning",
                "chat",
                "qa",
                name="dataset_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "format",
            sa.Enum(
                "csv",
                "json",
                "jsonl",
                name="dataset_format",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "uploading",
                "validating",
                "ready",
                "failed",
                "deleted",
                name="dataset_status",
                create_type=False,
            ),
            nullable=False,
            server_default="uploading",
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_datasets_name", "datasets", ["name"], unique=False
    )
    op.create_index(
        "ix_datasets_created_by", "datasets", ["created_by"], unique=False
    )

    # dataset_versions table
    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("validation_errors", sa.Text(), nullable=True),
        sa.Column("statistics", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_dataset_versions_dataset_id",
        "dataset_versions",
        ["dataset_id"],
        unique=False,
    )
    # Unique constraint: one version_number per dataset
    op.create_unique_constraint(
        "uq_dataset_versions_dataset_version",
        "dataset_versions",
        ["dataset_id", "version_number"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_dataset_versions_dataset_version",
        "dataset_versions",
        type_="unique",
    )
    op.drop_index(
        "ix_dataset_versions_dataset_id", table_name="dataset_versions"
    )
    op.drop_table("dataset_versions")
    op.drop_index("ix_datasets_created_by", table_name="datasets")
    op.drop_index("ix_datasets_name", table_name="datasets")
    op.drop_table("datasets")

    sa.Enum(name="dataset_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="dataset_format").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="dataset_type").drop(op.get_bind(), checkfirst=True)
