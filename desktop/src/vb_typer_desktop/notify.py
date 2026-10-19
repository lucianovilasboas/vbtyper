"""Notificações de desktop: nunca bloqueiam a thread do ditado."""

from __future__ import annotations

import shutil
import subprocess


def notify(title: str, message: str, urgency: str = "normal") -> None:
    command = shutil.which("notify-send")
    if not command:
        print(f"{title}: {message}", flush=True)
        return
    try:
        subprocess.Popen(
            [command, "--app-name=VB Typer", f"--urgency={urgency}", title, message],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        print(f"{title}: {message}", flush=True)
