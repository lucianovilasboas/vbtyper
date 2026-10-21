"""Corrige o `default_profile` herdado do modo antigo.

A migração 0003 copiou `mode` direto para `default_profile`: quem estava no modo
inteligente ficou com o valor "smart", que não é slug de perfil, e a criação de
jobs passava a falhar com 404 (perfil inexistente).

A correção é deliberadamente pontual: só o valor legado "smart" é trocado. Um
perfil personalizado válido nunca é tocado.

Revision ID: 0005_default_profile
Revises: 0004_job_phase
"""

from __future__ import annotations

from alembic import op

revision: str = "0005_default_profile"
down_revision: str | None = "0004_job_phase"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "update app_settings set default_profile = 'revisado' where default_profile = 'smart'"
    )


def downgrade() -> None:
    op.execute(
        "update app_settings set default_profile = 'smart' where default_profile = 'revisado'"
    )
