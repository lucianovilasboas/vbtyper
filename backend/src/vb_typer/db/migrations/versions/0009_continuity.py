"""Memória entre ditados: quantos anteriores entraram como contexto.

Fica no próprio ditado para o histórico mostrar quando o texto continuou outro
(``continuity_count``) e para conseguir auditar uma saída estranha.

Revision ID: 0009_continuity
Revises: 0008_editable_profiles
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0009_continuity"
down_revision: str | None = "0008_editable_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transcriptions",
        sa.Column("continuity_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("transcriptions", "continuity_count")
