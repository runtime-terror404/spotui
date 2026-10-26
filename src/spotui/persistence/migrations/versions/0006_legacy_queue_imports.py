"""Add the repeat-safe legacy queue migration ledger.

Revision ID: 0006_legacy_queue_imports
Revises: 0005_paired_devices
Create Date: 2026-10-26

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_legacy_queue_imports"
down_revision: str | None = "0005_paired_devices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "legacy_queue_imports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("legacy_key", sa.String(length=64), nullable=False),
        sa.Column("legacy_job_id", sa.String(length=64), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("job_id", sa.String(length=32), nullable=True),
        sa.Column("imported_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["download_jobs.id"],
            name="fk_legacy_queue_imports_job_id_download_jobs",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_legacy_queue_imports"),
        sa.CheckConstraint(
            "outcome IN ('imported', 'skipped', 'ambiguous', 'failed')",
            name="ck_legacy_queue_imports_outcome",
        ),
    )
    op.create_index(
        "ux_legacy_queue_imports_source_key",
        "legacy_queue_imports",
        ["source_path", "legacy_key"],
        unique=True,
    )
    op.create_index(
        "ix_legacy_queue_imports_source_path",
        "legacy_queue_imports",
        ["source_path"],
        unique=False,
    )
    op.create_index(
        "ix_legacy_queue_imports_job_id",
        "legacy_queue_imports",
        ["job_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_legacy_queue_imports_job_id",
        table_name="legacy_queue_imports",
    )
    op.drop_index(
        "ix_legacy_queue_imports_source_path",
        table_name="legacy_queue_imports",
    )
    op.drop_index(
        "ux_legacy_queue_imports_source_key",
        table_name="legacy_queue_imports",
    )
    op.drop_table("legacy_queue_imports")
