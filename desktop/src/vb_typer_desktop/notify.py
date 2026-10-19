"""Notificações de desktop: nunca bloqueiam a thread do ditado."""

from __future__ import annotations

import shutil
import subprocess


def notify(
    title: str,
    message: str,
    urgency: str = "normal",
    *,
    sound: bool = True,
    transient: bool = True,
) -> None:
    """Balão do sistema; ``sound=False`` pede silêncio pelo hint padrão."""
    command = shutil.which("notify-send")
    if not command:
        print(f"{title}: {message}", flush=True)
        return
    arguments = [command, "--app-name=VB Typer", f"--urgency={urgency}"]
    if transient:
        arguments.append("--transient")
    if not sound:
        arguments += ["-h", "boolean:suppress-sound:true"]
    arguments += [title, message]
    try:
        subprocess.Popen(
            arguments,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        print(f"{title}: {message}", flush=True)
