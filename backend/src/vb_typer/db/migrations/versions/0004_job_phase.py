"""Fase do job: transcrição ou ajuste do perfil.

O cliente acompanha o job por polling; sem esta coluna ele só saberia
``running`` e não conseguiria dizer se o servidor está transcrevendo o áudio ou
aplicando o perfil escolhido.

Revision ID: 0004_job_phase
Revises: 0003_profiles
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0004_job_phase"
down_revision: str | None = "0003_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("phase", sa.String(length=16), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("jobs", "phase")
