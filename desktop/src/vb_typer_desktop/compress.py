"""Conversão do WAV da captura para Opus antes do envio.

O ``arecord`` só escreve PCM: a mesma fala de 30 s ocupa ~960 KB, contra ~120 KB
do WebM/Opus que o navegador envia. Sobre a internet essa diferença é espera
pura, então o cliente comprime quando a API não está na própria máquina.

Nada aqui é obrigatório: sem ``ffmpeg``, ou se a conversão falhar, o WAV segue
como antes — a fluidez nunca pode custar o ditado.
"""

from __future__ import annotations

import contextlib
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

OPUS_BITRATE = "32k"
OPUS_SUFFIX = ".ogg"
OPUS_TIMEOUT_S = 20.0
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})


def is_loopback(base_url: str) -> bool:
    """A API está na própria máquina? (upload não custa rede)"""
    try:
        host = urlparse(base_url or "").hostname or ""
    except ValueError:
        return False
    return host.lower() in LOOPBACK_HOSTS


def should_compress(upload_format: str, base_url: str) -> bool:
    """Decide pelo formato escolhido: ``auto`` comprime só fora da máquina."""
    choice = (upload_format or "auto").strip().lower()
    if choice == "opus":
        return True
    if choice == "wav":
        return False
    return not is_loopback(base_url)


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def to_opus(
    wav: Path, *, bitrate: str = OPUS_BITRATE, timeout: float = OPUS_TIMEOUT_S
) -> Path | None:
    """Converte o WAV para Opus mono 16 kHz; ``None`` quando não dá para converter."""
    binary = shutil.which("ffmpeg")
    if not binary:
        return None
    target = Path(wav).with_suffix(OPUS_SUFFIX)
    command = [
        binary,
        "-nostdin",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(wav),
        "-c:a",
        "libopus",
        "-b:a",
        bitrate,
        "-ac",
        "1",
        "-ar",
        "16000",
        str(target),
    ]
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        target.unlink(missing_ok=True)
        return None
    if result.returncode != 0 or not target.is_file() or target.stat().st_size <= 0:
        target.unlink(missing_ok=True)
        return None
    with contextlib.suppress(OSError):
        target.chmod(0o600)
    return target
