"""Abertura da interface web no navegador, em modo app quando possível."""

from __future__ import annotations

import shutil
import subprocess
import webbrowser

# Navegadores baseados em Chromium aceitam ``--app=``, que abre uma janela sem
# barra de endereços nem abas. O Firefox não tem modo app: abre uma janela nova.
APP_MODE_BROWSERS = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "brave-browser",
    "microsoft-edge",
)


def ui_url(base_url: str = "http://127.0.0.1:8765") -> str:
    return base_url.rstrip("/") + "/"


def browser_command(url: str) -> list[str] | None:
    """Comando do navegador em modo app, ou ``None`` quando não há suporte."""
    for name in APP_MODE_BROWSERS:
        executable = shutil.which(name)
        if executable:
            return [executable, f"--app={url}"]
    firefox = shutil.which("firefox")
    if firefox:
        return [firefox, "--new-window", url]
    return None


def open_ui(base_url: str = "http://127.0.0.1:8765") -> bool:
    """Abre a interface e devolve se conseguiu iniciar um navegador."""
    url = ui_url(base_url)
    command = browser_command(url)
    if command is None:
        return bool(webbrowser.open(url))
    try:
        subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return bool(webbrowser.open(url))
    return True
