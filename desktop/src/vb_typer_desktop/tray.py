"""Processos auxiliares GTK3: bandeja do sistema e indicador de ditado.

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
INDICATOR_RELATIVE = "tray/indicator.py"
ASSETS_RELATIVE = "assets"


def resource_base() -> Path:
    """Raiz dos arquivos embarcados, na árvore de código ou no executável one-file."""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled)
    return Path(__file__).resolve().parents[2]


def resource_path(relative: str) -> Path:
    return resource_base() / relative


def gtklib_available() -> bool:
    """O 1.x usa o ``gdbus`` como sinal barato de que o GTK do sistema existe."""
    return bool(shutil.which("gdbus") and Path(SYSTEM_PYTHON).exists())


def tray_available() -> bool:
    return gtklib_available() and resource_path(HELPER_RELATIVE).exists()


def indicator_available() -> bool:
    return gtklib_available() and resource_path(INDICATOR_RELATIVE).exists()


def _spawn(relative: str, arguments: list[str]) -> subprocess.Popen[bytes] | None:
    try:
        return subprocess.Popen(
            [SYSTEM_PYTHON, str(resource_path(relative)), *arguments],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return None


def start_tray(socket_path: Path) -> subprocess.Popen[bytes] | None:
    """Sobe o helper da bandeja; ``None`` quando o ambiente não o suporta."""
    if not tray_available():
        return None
    return _spawn(HELPER_RELATIVE, [str(socket_path), str(resource_path(ASSETS_RELATIVE))])


def start_indicator(
    socket_path: Path,
    speed: float = 1.0,
    sensitivity: float = 1.0,
    shape: str = "wave",
) -> subprocess.Popen[bytes] | None:
    """Sobe o indicador visual; ``None`` quando o ambiente não o suporta."""
    if not indicator_available():
        return None
    return _spawn(
        INDICATOR_RELATIVE,
        [
            str(socket_path),
            f"--speed={speed:.2f}",
            f"--sensitivity={sensitivity:.2f}",
            f"--shape={shape}",
        ],
    )
