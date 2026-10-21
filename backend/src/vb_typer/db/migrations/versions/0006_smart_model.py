"""Modelo de texto (segunda etapa) nas configurações.

Antes ele vinha só do ambiente; agora a escolha do usuário vive no banco, com a
variável de ambiente servindo de valor inicial.

Revision ID: 0006_smart_model
Revises: 0005_default_profile
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0006_smart_model"
down_revision: str | None = "0005_default_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column(
            "smart_model", sa.String(length=64), nullable=False, server_default="gpt-4o-mini"
        ),
    )


def downgrade() -> None:
    op.drop_column("app_settings", "smart_model")
