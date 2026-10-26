"""Destino de entrega e ferramentas aplicadas ao texto.

`delivery` diz como o texto foi preparado ("text", "tui", ...); `tools` guarda
as ferramentas efetivas, incluindo a expansão do preset do destino. O cliente
usa o destino para aplicar a guarda final antes de inserir.

Revision ID: 0010_delivery_tools
Revises: 0009_continuity
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0010_delivery_tools"
down_revision: str | None = "0009_continuity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transcriptions",
        sa.Column("delivery", sa.String(length=20), nullable=False, server_default="text"),
    )
    op.add_column(
        "transcriptions",
        sa.Column("tools", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("transcriptions", "tools")
    op.drop_column("transcriptions", "delivery")
