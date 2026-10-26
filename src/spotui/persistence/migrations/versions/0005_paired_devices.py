"""Add trusted paired-device credentials.

Revision ID: 0005_paired_devices
Revises: 0004_spotify_imports
Create Date: 2026-10-26

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_paired_devices"
down_revision: str | None = "0004_spotify_imports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "paired_devices",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("credential_hash", sa.String(length=64), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("last_seen_at", sa.Integer(), nullable=True),
        sa.Column("last_seen_ip", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("revoked_at", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_paired_devices"),
    )
    op.create_index(
        "ux_paired_devices_credential_hash",
        "paired_devices",
        ["credential_hash"],
        unique=True,
    )
    op.create_index(
        "ix_paired_devices_revoked_at",
        "paired_devices",
        ["revoked_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_paired_devices_revoked_at", table_name="paired_devices")
    op.drop_index(
        "ux_paired_devices_credential_hash",
        table_name="paired_devices",
    )
    op.drop_table("paired_devices")
