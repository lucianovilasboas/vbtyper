"""Fixtures dos testes do cliente desktop."""

from __future__ import annotations

import wave
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path_factory, monkeypatch):
    """Nunca tocar na configuração, no token ou nos dados reais do usuário."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path_factory.mktemp("config")))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path_factory.mktemp("runtime")))
    monkeypatch.delenv("VB_TYPER_API_TOKEN", raising=False)


@pytest.fixture
def make_wav():
    """Cria um WAV PCM mono 16 kHz válido (o formato que o arecord produz)."""

    def build(path: Path, seconds: float = 0.5) -> Path:
        frames = int(16000 * seconds) * 2
        with wave.open(str(path), "wb") as handle:
            handle.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            handle.writeframes(bytes(frames))
        return Path(path)

    return build
