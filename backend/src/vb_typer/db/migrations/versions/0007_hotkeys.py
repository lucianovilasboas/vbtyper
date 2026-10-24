"""Atalhos do cliente desktop nas configurações.

A combinação de teclas é por instalação (backend), para poder ser editada na aba
Configurações da interface web. O cliente desktop só lê e aplica.

Revision ID: 0007_hotkeys
Revises: 0006_smart_model
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0007_hotkeys"
down_revision: str | None = "0006_smart_model"
branch_labels = None
depends_on = None

# Padrões copiados do domínio: a migração guarda o valor da época, de propósito.
DEFAULT_HOTKEYS = (
    '{"profile_next": "ctrl+alt+Tab", "profile_previous": "ctrl+alt+shift+Tab", '
    '"profile_default": "ctrl+alt+0"}'
)


def upgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column("hotkeys", sa.JSON(), nullable=False, server_default=DEFAULT_HOTKEYS),
    )


def downgrade() -> None:
    op.drop_column("app_settings", "hotkeys")
