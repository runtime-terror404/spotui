"""Add download job attempt history.

Revision ID: 0002_job_attempts
Revises: 0001_initial
Create Date: 2026-10-26

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_job_attempts"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TERMINAL_STATES = (
    "outcome IS NULL OR outcome IN "
    "('completed', 'failed', 'cancelled', 'interrupted')"
)


def upgrade() -> None:
    op.create_table(
        "job_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=32), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.Integer(), nullable=False),
        sa.Column("finished_at", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("output_path", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["download_jobs.id"],
            name="fk_job_attempts_job_id_download_jobs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_job_attempts"),
        sa.CheckConstraint("attempt_number > 0", name="attempt_number_positive"),
        sa.CheckConstraint(_TERMINAL_STATES, name="outcome"),
    )
    op.create_index(
        "ux_job_attempts_job_attempt",
        "job_attempts",
        ["job_id", "attempt_number"],
        unique=True,
    )
    op.create_index(
        "ix_job_attempts_job_id_started_at",
        "job_attempts",
        ["job_id", "started_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_job_attempts_job_id_started_at", table_name="job_attempts")
    op.drop_index("ux_job_attempts_job_attempt", table_name="job_attempts")
    op.drop_table("job_attempts")
