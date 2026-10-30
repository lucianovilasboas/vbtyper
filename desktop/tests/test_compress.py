"""Envio comprimido: quando comprimir e o que fazer quando o ffmpeg falha."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from vb_typer_desktop import compress

REMOTE = "https://vbtyper.lucianovilasboas.com.br"
LOCAL = "http://127.0.0.1:8765"


@pytest.mark.parametrize(
    "url",
    [LOCAL, "http://localhost:8765", "http://[::1]:8765"],
)
def test_loopback_apis_do_not_need_compression(url):
    assert compress.is_loopback(url)
    assert compress.should_compress("auto", url) is False


def test_remote_api_is_compressed_in_auto_mode():
    assert compress.is_loopback(REMOTE) is False
    assert compress.should_compress("auto", REMOTE) is True


def test_the_choice_can_be_forced():
    assert compress.should_compress("opus", LOCAL) is True
    assert compress.should_compress("wav", REMOTE) is False
    assert compress.should_compress("", REMOTE) is True  # vazio lê como auto


def test_a_broken_url_is_treated_as_remote():
    assert compress.is_loopback("isso não é url") is False


def test_conversion_returns_none_without_ffmpeg(monkeypatch, tmp_path):
    monkeypatch.setattr(compress.shutil, "which", lambda name: None)
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    assert compress.to_opus(wav) is None
    assert not (tmp_path / "a.ogg").exists()


def test_conversion_returns_the_opus_file(monkeypatch, tmp_path):
    wav = tmp_path / "captura.wav"
    wav.write_bytes(b"RIFF")
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"OggS" + b"\0" * 32)
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(compress.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(compress.subprocess, "run", fake_run)

    result = compress.to_opus(wav)

    assert result == tmp_path / "captura.ogg"
    assert result.is_file()
    assert "-c:a" in commands[0] and "libopus" in commands[0]
    assert commands[0][-1] == str(result)


def test_a_failed_conversion_leaves_no_partial_file(monkeypatch, tmp_path):
    wav = tmp_path / "captura.wav"
    wav.write_bytes(b"RIFF")

    def failing_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"lixo")
        return subprocess.CompletedProcess(command, 1, b"", b"erro")

    monkeypatch.setattr(compress.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(compress.subprocess, "run", failing_run)

    assert compress.to_opus(wav) is None
    assert not (tmp_path / "captura.ogg").exists()


def test_a_timeout_is_not_an_error(monkeypatch, tmp_path):
    wav = tmp_path / "captura.wav"
    wav.write_bytes(b"RIFF")

    def timing_out(command, **kwargs):
        Path(command[-1]).write_bytes(b"lixo")
        raise subprocess.TimeoutExpired(command, 1)

    monkeypatch.setattr(compress.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(compress.subprocess, "run", timing_out)

    assert compress.to_opus(wav) is None
    assert not (tmp_path / "captura.ogg").exists()
