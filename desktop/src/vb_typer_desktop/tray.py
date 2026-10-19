"""Bandeja do sistema: ícones e menu, por um processo auxiliar GTK3.

O Python do sistema é usado porque o PyGObject/GTK não empacota bem no
PyInstaller; a comunicação é feita pelo socket de controle (um JSON por linha).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

SYSTEM_PYTHON = "/usr/bin/python3"
HELPER_RELATIVE = "tray/tray_helper.py"
ASSETS_RELATIVE = "assets"


def resource_base() -> Path:
    """Raiz dos arquivos embarcados, na árvore de código ou no executável one-file."""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled)
    return Path(__file__).resolve().parents[2]


def resource_path(relative: str) -> Path:
    return resource_base() / relative


def tray_available() -> bool:
    return bool(
        shutil.which("gdbus")
        and Path(SYSTEM_PYTHON).exists()
        and resource_path(HELPER_RELATIVE).exists()
    )


def start_tray(socket_path: Path) -> subprocess.Popen[bytes] | None:
    """Sobe o helper da bandeja; ``None`` quando o ambiente não o suporta."""
    if not tray_available():
        return None
    try:
        return subprocess.Popen(
            [
                SYSTEM_PYTHON,
                str(resource_path(HELPER_RELATIVE)),
                str(socket_path),
                str(resource_path(ASSETS_RELATIVE)),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return None
