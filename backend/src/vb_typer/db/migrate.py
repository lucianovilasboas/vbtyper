"""Executor de migrações programático."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from vb_typer.db.session import database_url


def migrations_dir() -> Path:
    return Path(__file__).resolve().parent / "migrations"


def alembic_config(url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(migrations_dir()))
    config.set_main_option("sqlalchemy.url", url)
    return config


def upgrade(database: Path) -> None:
    """Aplica todas as migrações pendentes."""
    command.upgrade(alembic_config(database_url(database)), "head")
