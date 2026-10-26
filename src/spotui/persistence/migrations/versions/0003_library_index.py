"""Add the read-only library index.

Revision ID: 0003_library_index
Revises: 0002_job_attempts
Create Date: 2026-10-26

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_library_index"
down_revision: str | None = "0002_job_attempts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCAN_STATUSES = "status IN ('running', 'completed', 'failed', 'interrupted')"
_METADATA_SOURCES = "metadata_source IN ('tags', 'filename')"


def upgrade() -> None:
    op.create_table(
        "library_roots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("available", sa.Boolean(), nullable=False),
        sa.Column("index_complete", sa.Boolean(), nullable=False),
        sa.Column("last_checked_at", sa.Integer(), nullable=True),
        sa.Column("last_scan_at", sa.Integer(), nullable=True),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_library_roots"),
        sa.CheckConstraint("file_count >= 0", name="file_count_nonnegative"),
    )
    op.create_index(
        "ux_library_roots_path",
        "library_roots",
        ["path"],
        unique=True,
    )

    op.create_table(
        "library_files",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("root_id", sa.Integer(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("extension", sa.String(length=16), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("modified_at_ns", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("artist", sa.Text(), nullable=False),
        sa.Column("album", sa.Text(), nullable=False),
        sa.Column("track_number", sa.Text(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("metadata_source", sa.String(length=20), nullable=False),
        sa.Column("normalized_title", sa.Text(), nullable=False),
        sa.Column("normalized_artist", sa.Text(), nullable=False),
        sa.Column("amazon_track_key", sa.String(length=128), nullable=True),
        sa.Column("last_seen_scan_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["root_id"],
            ["library_roots.id"],
            name="fk_library_files_root_id_library_roots",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_library_files"),
        sa.CheckConstraint("size_bytes >= 0", name="size_nonnegative"),
        sa.CheckConstraint("modified_at_ns >= 0", name="modified_nonnegative"),
        sa.CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0",
            name="duration_nonnegative",
        ),
        sa.CheckConstraint(_METADATA_SOURCES, name="metadata_source"),
    )
    op.create_index(
        "ux_library_files_root_path",
        "library_files",
        ["root_id", "path"],
        unique=True,
    )
    op.create_index(
        "ix_library_files_normalized_title",
        "library_files",
        ["normalized_title"],
        unique=False,
    )
    op.create_index(
        "ix_library_files_amazon_track_key",
        "library_files",
        ["amazon_track_key"],
        unique=False,
    )
    op.create_index(
        "ix_library_files_root_last_seen",
        "library_files",
        ["root_id", "last_seen_scan_id"],
        unique=False,
    )

    op.create_table(
        "library_scan_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("root_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.Integer(), nullable=False),
        sa.Column("finished_at", sa.Integer(), nullable=True),
        sa.Column("files_seen", sa.Integer(), nullable=False),
        sa.Column("files_indexed", sa.Integer(), nullable=False),
        sa.Column("files_removed", sa.Integer(), nullable=False),
        sa.Column("files_failed", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["root_id"],
            ["library_roots.id"],
            name="fk_library_scan_runs_root_id_library_roots",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_library_scan_runs"),
        sa.CheckConstraint(_SCAN_STATUSES, name="status"),
        sa.CheckConstraint("files_seen >= 0", name="files_seen_nonnegative"),
        sa.CheckConstraint("files_indexed >= 0", name="files_indexed_nonnegative"),
        sa.CheckConstraint("files_removed >= 0", name="files_removed_nonnegative"),
        sa.CheckConstraint("files_failed >= 0", name="files_failed_nonnegative"),
    )
    op.create_index(
        "ux_library_scan_runs_active",
        "library_scan_runs",
        ["status"],
        unique=True,
        sqlite_where=sa.text("status = 'running'"),
    )
    op.create_index(
        "ix_library_scan_runs_root_started",
        "library_scan_runs",
        ["root_id", "started_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_library_scan_runs_root_started",
        table_name="library_scan_runs",
    )
    op.drop_index(
        "ux_library_scan_runs_active",
        table_name="library_scan_runs",
    )
    op.drop_table("library_scan_runs")
    op.drop_index("ix_library_files_root_last_seen", table_name="library_files")
    op.drop_index("ix_library_files_amazon_track_key", table_name="library_files")
    op.drop_index("ix_library_files_normalized_title", table_name="library_files")
    op.drop_index("ux_library_files_root_path", table_name="library_files")
    op.drop_table("library_files")
    op.drop_index("ux_library_roots_path", table_name="library_roots")
    op.drop_table("library_roots")
