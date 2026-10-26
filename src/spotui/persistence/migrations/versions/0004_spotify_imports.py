"""Add Spotify import sessions, source occurrences, and candidates.

Revision ID: 0004_spotify_imports
Revises: 0003_library_index
Create Date: 2026-10-26

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_spotify_imports"
down_revision: str | None = "0003_library_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUSES = "status IN ('extracting', 'matching', 'paused', 'matching_complete')"
_SPOTIFY_TYPES = "spotify_type IS NULL OR spotify_type IN ('album', 'playlist')"
_MATCHING_STATUSES = (
    "matching_status IN "
    "('pending', 'searching', 'candidates_ready', 'no_results', 'failed')"
)
_REVIEW_STATUSES = "review_status IN ('unreviewed', 'selected', 'skipped')"
_QUEUE_OUTCOMES = (
    "queue_outcome IN ('none', 'queued', 'duplicate', 'skipped_library')"
)
_LIBRARY_MATCHES = "library_match IS NULL OR library_match IN ('exact', 'likely')"


def upgrade() -> None:
    op.create_table(
        "import_sessions",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("spotify_type", sa.String(length=16), nullable=True),
        sa.Column("spotify_id", sa.String(length=32), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("artwork_url", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("active_slot", sa.Integer(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.Column("matching_started_at", sa.Integer(), nullable=True),
        sa.Column("matching_completed_at", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_import_sessions"),
        sa.CheckConstraint(_STATUSES, name="status"),
        sa.CheckConstraint(_SPOTIFY_TYPES, name="spotify_type"),
        sa.CheckConstraint(
            "(status = 'matching_complete' AND active_slot IS NULL) OR "
            "(status IN ('extracting', 'matching', 'paused') AND active_slot = 1)",
            name="active_slot_matches_status",
        ),
        sa.CheckConstraint("revision >= 0", name="revision_nonnegative"),
    )
    op.create_index(
        "ux_import_sessions_active",
        "import_sessions",
        ["active_slot"],
        unique=True,
        sqlite_where=sa.text("active_slot IS NOT NULL"),
    )
    op.create_index(
        "ix_import_sessions_status_created",
        "import_sessions",
        ["status", "created_at"],
        unique=False,
    )

    op.create_table(
        "source_tracks",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("session_id", sa.String(length=32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("spotify_track_id", sa.String(length=32), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("artist", sa.Text(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("matching_status", sa.String(length=20), nullable=False),
        sa.Column("review_status", sa.String(length=20), nullable=False),
        sa.Column("selected_candidate_id", sa.String(length=32), nullable=True),
        sa.Column("library_match", sa.String(length=8), nullable=True),
        sa.Column("queue_outcome", sa.String(length=20), nullable=False),
        sa.Column("queued_job_id", sa.String(length=32), nullable=True),
        sa.Column("source_duplicate_of_id", sa.String(length=32), nullable=True),
        sa.Column("queued_duplicate_of_source_id", sa.String(length=32), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["import_sessions.id"],
            name="fk_source_tracks_session_id_import_sessions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_source_tracks"),
        sa.CheckConstraint("position >= 0", name="position_nonnegative"),
        sa.CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        sa.CheckConstraint(_MATCHING_STATUSES, name="matching_status"),
        sa.CheckConstraint(_REVIEW_STATUSES, name="review_status"),
        sa.CheckConstraint(_QUEUE_OUTCOMES, name="queue_outcome"),
        sa.CheckConstraint(_LIBRARY_MATCHES, name="library_match"),
        sa.CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0",
            name="duration_nonnegative",
        ),
    )
    op.create_index(
        "ux_source_tracks_session_position",
        "source_tracks",
        ["session_id", "position"],
        unique=True,
    )
    op.create_index(
        "ix_source_tracks_session_matching",
        "source_tracks",
        ["session_id", "matching_status"],
        unique=False,
    )

    op.create_table(
        "amazon_candidates",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("source_track_id", sa.String(length=32), nullable=False),
        sa.Column("track_url", sa.Text(), nullable=False),
        sa.Column("track_key", sa.String(length=128), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("artist", sa.Text(), nullable=False),
        sa.Column("album", sa.Text(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("artwork_url", sa.Text(), nullable=True),
        sa.Column("provider_position", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_track_id"],
            ["source_tracks.id"],
            name="fk_amazon_candidates_source_track_id_source_tracks",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_amazon_candidates"),
        sa.CheckConstraint(
            "provider_position >= 0",
            name="provider_position_nonnegative",
        ),
        sa.CheckConstraint("rank > 0", name="rank_positive"),
        sa.CheckConstraint("score >= 0 AND score <= 1", name="score_range"),
        sa.CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0",
            name="duration_nonnegative",
        ),
    )
    op.create_index(
        "ux_amazon_candidates_source_track_key",
        "amazon_candidates",
        ["source_track_id", "track_key"],
        unique=True,
    )
    op.create_index(
        "ix_amazon_candidates_source_rank",
        "amazon_candidates",
        ["source_track_id", "rank"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_amazon_candidates_source_rank",
        table_name="amazon_candidates",
    )
    op.drop_index(
        "ux_amazon_candidates_source_track_key",
        table_name="amazon_candidates",
    )
    op.drop_table("amazon_candidates")
    op.drop_index(
        "ix_source_tracks_session_matching",
        table_name="source_tracks",
    )
    op.drop_index(
        "ux_source_tracks_session_position",
        table_name="source_tracks",
    )
    op.drop_table("source_tracks")
    op.drop_index(
        "ix_import_sessions_status_created",
        table_name="import_sessions",
    )
    op.drop_index("ux_import_sessions_active", table_name="import_sessions")
    op.drop_table("import_sessions")
