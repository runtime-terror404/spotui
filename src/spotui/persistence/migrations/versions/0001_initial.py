"""Initial download job schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-26

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIVE_STATES = "state IN ('queued', 'starting', 'running', 'cancelling')"
_ALL_STATES = (
    "state IN ('queued', 'starting', 'running', 'cancelling', "
    "'completed', 'failed', 'cancelled', 'interrupted')"
)


def upgrade() -> None:
    op.create_table(
        "download_jobs",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("track_url", sa.Text(), nullable=False),
        sa.Column("track_key", sa.String(length=128), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("artist", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("status_message", sa.Text(), nullable=False),
        sa.Column("progress_phase", sa.String(length=40), nullable=True),
        sa.Column("progress_percent", sa.Float(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("output_path", sa.Text(), nullable=True),
        sa.Column("source_import_id", sa.String(length=36), nullable=True),
        sa.Column("source_occurrence_id", sa.String(length=36), nullable=True),
        sa.Column("source_playlist_title", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_download_jobs"),
        sa.CheckConstraint(_ALL_STATES, name="state"),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="attempt_count_nonnegative",
        ),
        sa.CheckConstraint(
            "progress_percent IS NULL OR "
            "(progress_percent >= 0 AND progress_percent <= 100)",
            name="progress_percent_range",
        ),
    )
    op.create_index(
        "ix_download_jobs_state_created_at",
        "download_jobs",
        ["state", "created_at"],
        unique=False,
    )
    op.create_index(
        "ux_download_jobs_active_track_key",
        "download_jobs",
        ["track_key"],
        unique=True,
        sqlite_where=sa.text(_ACTIVE_STATES),
    )


def downgrade() -> None:
    op.drop_index("ux_download_jobs_active_track_key", table_name="download_jobs")
    op.drop_index("ix_download_jobs_state_created_at", table_name="download_jobs")
    op.drop_table("download_jobs")
