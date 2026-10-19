"""Modo de transcrição (literal/inteligente) no job, no histórico e nas configs.

O texto cru da transcrição fica guardado em ``transcriptions.raw_text`` para
auditar o ajuste do modo inteligente e poder voltar atrás.

Revision ID: 0002_modes
Revises: 0001_initial
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0002_modes"
down_revision: str | None = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="literal"),
    )
    op.add_column(
        "transcriptions",
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="literal"),
    )
    op.add_column("transcriptions", sa.Column("raw_text", sa.Text(), nullable=True))
    op.add_column(
        "app_settings",
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="literal"),
    )


def downgrade() -> None:
    op.drop_column("app_settings", "mode")
    op.drop_column("transcriptions", "raw_text")
    op.drop_column("transcriptions", "mode")
    op.drop_column("jobs", "mode")
