"""Perfis no banco: semente única, ordem e marca dos padrões.

`profiles.seeded` marca os perfis que vieram do padrão (badge "padrão");
continuam editáveis e removíveis, com exceção da transcrição fiel.
`sort_order` preserva a ordem curada dos padrões; os personalizados continuam
alfabéticos. `app_settings.profiles_seeded` garante que a semente roda uma vez
só — um perfil apagado nunca volta.

Revision ID: 0008_editable_profiles
Revises: 0007_hotkeys
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0008_editable_profiles"
down_revision: str | None = "0007_hotkeys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "profiles",
        sa.Column("seeded", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "profiles",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "app_settings",
        sa.Column("profiles_seeded", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    # O código antigo lista os padrões a partir do código: deixar as linhas
    # semeadas no banco as duplicaria na lista.
    op.execute("DELETE FROM profiles WHERE seeded = 1")
    op.drop_column("app_settings", "profiles_seeded")
    op.drop_column("profiles", "sort_order")
    op.drop_column("profiles", "seeded")
