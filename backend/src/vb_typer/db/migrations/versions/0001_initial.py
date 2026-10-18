"""Esquema inicial: transcrições, jobs e configurações.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transcriptions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.String(length=19), nullable=False),
        sa.Column("audio_path", sa.Text(), nullable=True),
        sa.Column("audio_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_s", sa.Float(), nullable=False, server_default="0"),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("words", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("language", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("transcribe_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("insert_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inserted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("legacy_source", sa.String(length=255), nullable=True),
        sa.Column("legacy_id", sa.Integer(), nullable=True),
        sa.UniqueConstraint("legacy_source", "legacy_id", name="uq_transcriptions_legacy"),
    )
    op.create_index("ix_transcriptions_created_at", "transcriptions", ["created_at"], unique=False)

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.String(length=19), nullable=False),
        sa.Column("updated_at", sa.String(length=19), nullable=False),
        sa.Column("started_at", sa.String(length=19), nullable=True),
        sa.Column("finished_at", sa.String(length=19), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("content_type", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_s", sa.Float(), nullable=False, server_default="0"),
        sa.Column("audio_path", sa.Text(), nullable=True),
        sa.Column(
            "transcription_id",
            sa.Integer(),
            sa.ForeignKey("transcriptions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_jobs_status", "jobs", ["status"], unique=False)
    op.create_index("ix_jobs_created_at", "jobs", ["created_at"], unique=False)

    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("week_start", sa.String(length=16), nullable=False, server_default="monday"),
        sa.Column("updated_at", sa.String(length=19), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_index("ix_jobs_created_at", table_name="jobs")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_transcriptions_created_at", table_name="transcriptions")
    op.drop_table("transcriptions")
