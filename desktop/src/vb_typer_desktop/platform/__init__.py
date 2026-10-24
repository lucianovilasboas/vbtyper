"""Adaptadores de plataforma do cliente desktop."""

from __future__ import annotations

import sys

from vb_typer_desktop.platform.base import ComboWatcher, HotkeyWatcher, Platform

__all__ = ["ComboWatcher", "HotkeyWatcher", "Platform", "get_platform"]


def get_platform() -> Platform:
    """Devolve o adaptador do sistema operacional atual."""
    if sys.platform.startswith("linux"):
        from vb_typer_desktop.platform.linux_x11 import LinuxX11Platform

        return LinuxX11Platform()
    raise RuntimeError(
        f"Ainda não há adaptador de ditado para {sys.platform}; por enquanto só Linux/X11."
    )
