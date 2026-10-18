"""Armazenamento dos áudios recebidos, sem expô-los pela API."""

from __future__ import annotations

import contextlib
import os
import struct
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from vb_typer.domain.errors import (
    AudioTooLargeError,
    InvalidAudioError,
    UnsupportedMediaTypeError,
)

CONTENT_TYPE_EXTENSIONS = {
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/m4a": ".m4a",
}

GENERIC_CONTENT_TYPES = {"application/octet-stream", ""}

EXTENSION_CONTENT_TYPES = {
    ".wav": "audio/wav",
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
}


@dataclass(frozen=True)
class StoredAudio:
    path: Path
    size: int
    content_type: str
    filename: str
    duration_s: float


def normalized_content_type(value: str | None, filename: str = "") -> str:
    content_type = (value or "").split(";", 1)[0].strip().lower()
    if content_type in GENERIC_CONTENT_TYPES:
        suffix = Path(filename or "").suffix.lower()
        content_type = EXTENSION_CONTENT_TYPES.get(suffix, "")
    return content_type


def wav_duration(data: bytes) -> float:
    """Duração de um WAV PCM mono 16 bits; ``0`` quando não dá para saber."""
    try:
        if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
            return 0.0
        offset = 12
        byte_rate = 0
        pcm_size = 0
        while offset + 8 <= len(data):
            name, size = struct.unpack_from("<4sI", data, offset)
            start = offset + 8
            end = start + size
            if end > len(data):
                return 0.0
            if name == b"fmt " and size >= 16:
                # format_tag, channels, sample_rate, byte_rate, block_align, bits
                _format, _channels, _rate, byte_rate, _align, _bits = struct.unpack_from(
                    "<HHIIHH", data, start
                )
            elif name == b"data":
                pcm_size = size
            offset = end + (size & 1)
        if byte_rate <= 0 or pcm_size <= 0:
            return 0.0
        return round(pcm_size / byte_rate, 3)
    except (struct.error, ValueError):
        return 0.0


def duration_of(data: bytes, content_type: str) -> float:
    if content_type in {"audio/wav", "audio/x-wav", "audio/wave"}:
        return wav_duration(data)
    return 0.0


class AudioStore:
    def __init__(self, root: Path, max_bytes: int, allowed_content_types: tuple[str, ...]) -> None:
        self.root = Path(root)
        self.max_bytes = max_bytes
        self.allowed_content_types = {item.lower() for item in allowed_content_types}

    def save(self, data: bytes, content_type: str, filename: str = "") -> StoredAudio:
        if not data:
            raise InvalidAudioError("O áudio está vazio.")
        if len(data) > self.max_bytes:
            raise AudioTooLargeError(
                f"O áudio excede o limite de {self.max_bytes // (1024 * 1024)} MB."
            )
        safe_type = normalized_content_type(content_type, filename)
        if safe_type not in self.allowed_content_types:
            raise UnsupportedMediaTypeError(
                f"Formato de áudio não suportado: {safe_type or 'desconhecido'}."
            )

        extension = CONTENT_TYPE_EXTENSIONS.get(safe_type, ".bin")
        now = time.localtime()
        folder = self.root / time.strftime("%Y", now) / time.strftime("%m", now)
        folder.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S", now)
        destination = folder / f"{stamp}-{uuid.uuid4().hex[:12]}{extension}"
        destination.write_bytes(data)
        with contextlib.suppress(OSError):
            os.chmod(destination, 0o600)
        return StoredAudio(
            path=destination,
            size=len(data),
            content_type=safe_type,
            filename=destination.name,
            duration_s=duration_of(data, safe_type),
        )

    def delete(self, path: str | Path | None) -> None:
        if not path:
            return
        with contextlib.suppress(OSError):
            Path(path).unlink(missing_ok=True)
