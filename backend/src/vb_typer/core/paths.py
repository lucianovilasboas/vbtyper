"""Resolução de diretórios e arquivos da aplicação.

No Linux os diretórios coincidem com o app 1.x (``~/.config/vibe-typer`` e
``~/.local/share/vb-typer``), mas o banco tem nome próprio para nunca colidir
com o ``history.db`` da versão 1.x.
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir

from vb_typer.core.config import AppSettings

APP_SLUG = "vb-typer"
DATABASE_FILENAME = "vb-typer.db"
TOKEN_FILENAME = "api-token"


@dataclass(frozen=True)
class AppPaths:
    config_dir: Path
    data_dir: Path
    database: Path
    audio_dir: Path
    token_file: Path


def resolve_paths(settings: AppSettings) -> AppPaths:
    config_dir = settings.config_dir or Path(user_config_dir(APP_SLUG, appauthor=False))
    data_dir = settings.data_dir or Path(user_data_dir(APP_SLUG, appauthor=False))
    database = settings.database_path or (data_dir / DATABASE_FILENAME)
    return AppPaths(
        config_dir=Path(config_dir),
        data_dir=Path(data_dir),
        database=Path(database),
        audio_dir=Path(data_dir) / "audio",
        token_file=Path(config_dir) / TOKEN_FILENAME,
    )


def _private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(path, 0o700)


def secure_file(path: Path) -> None:
    """Restringe um arquivo (banco, token) ao usuário atual."""
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)


def ensure_paths(paths: AppPaths) -> AppPaths:
    """Cria os diretórios necessários com permissão restrita ao usuário."""
    _private_dir(paths.config_dir)
    _private_dir(paths.data_dir)
    _private_dir(paths.audio_dir)
    return paths
