"""Perfis de texto e versões do ditado.

`profiles` guarda só os perfis **personalizados**; os embutidos vivem no código
(`domain/profiles.py`), versionados junto com o app.

`transcription_versions` guarda cada geração editorial, sempre a partir de
`transcriptions.raw_text` — nunca de outra versão já editada.

Revision ID: 0003_profiles
Revises: 0002_modes
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0003_profiles"
down_revision: str | None = "0002_modes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("hint", sa.Text(), nullable=True),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(length=19), nullable=False),
        sa.Column("updated_at", sa.String(length=19), nullable=False),
    )
    op.create_index("ix_profiles_slug", "profiles", ["slug"], unique=True)

    op.create_table(
        "transcription_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("transcription_id", sa.Integer(), nullable=False),
        sa.Column("profile", sa.String(length=40), nullable=False, server_default="literal"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.String(length=19), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["transcription_id"], ["transcriptions.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_transcription_versions_transcription_id",
        "transcription_versions",
        ["transcription_id"],
    )

    op.add_column(
        "transcriptions",
        sa.Column("profile", sa.String(length=40), nullable=False, server_default="literal"),
    )
    op.add_column(
        "jobs",
        sa.Column("profile", sa.String(length=40), nullable=False, server_default="literal"),
    )
    op.add_column(
        "app_settings",
        sa.Column(
            "default_profile", sa.String(length=40), nullable=False, server_default="literal"
        ),
    )

    # Quem já usava o modo inteligente mantém o comportamento: perfil revisado.
    op.execute("update transcriptions set profile = 'revisado' where mode = 'smart'")
    op.execute("update jobs set profile = 'revisado' where mode = 'smart'")
    op.execute("update app_settings set default_profile = mode")


def downgrade() -> None:
    op.drop_column("app_settings", "default_profile")
    op.drop_column("jobs", "profile")
    op.drop_column("transcriptions", "profile")
    op.drop_index("ix_transcription_versions_transcription_id", table_name="transcription_versions")
    op.drop_table("transcription_versions")
    op.drop_index("ix_profiles_slug", table_name="profiles")
    op.drop_table("profiles")
