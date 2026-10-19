"""Áudio: validação do WAV, reparo do RIFF e encerramento do arecord."""

from __future__ import annotations

import subprocess
from unittest.mock import Mock

import pytest

from vb_typer_desktop import audio


def test_accepts_valid_wav(make_wav, tmp_path):
    path = make_wav(tmp_path / "ok.wav", seconds=0.5)
    assert audio.validate_wav(path) == pytest.approx(0.5, abs=0.02)


def test_rejects_empty_file(tmp_path):
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    with pytest.raises(audio.AudioError):
        audio.validate_wav(empty)


def test_rejects_bad_signature(tmp_path):
    path = tmp_path / "bad.wav"
    path.write_bytes(b"NOPE" + bytes(100))
    with pytest.raises(audio.AudioError, match="RIFF"):
        audio.validate_wav(path)


def test_rejects_trailing_garbage(make_wav, tmp_path):
    path = make_wav(tmp_path / "trailing.wav", seconds=0.5)
    path.write_bytes(path.read_bytes() + b"\x00\x00")
    with pytest.raises(audio.AudioError):
        audio.validate_wav(path)


def test_rejects_duration_beyond_elapsed(make_wav, tmp_path):
    path = make_wav(tmp_path / "long.wav", seconds=5.0)
    with pytest.raises(audio.AudioError, match="Duração"):
        audio.validate_wav(path, elapsed=1.0)


def test_repair_handles_arecord_predicted_duration(tmp_path):
    """``arecord -d 120`` declara 120 s; o SIGINT deixa o declarado maior que os bytes."""
    declared = 120 * 32000
    pcm = bytes(20000)
    path = tmp_path / "cut.wav"
    path.write_bytes(
        b"RIFF"
        + (declared + 36).to_bytes(4, "little")
        + b"WAVE"
        + b"fmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (16000).to_bytes(4, "little")
        + (32000).to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data"
        + declared.to_bytes(4, "little")
        + pcm
    )
    assert audio.repair_interrupted_wav_header(path) is True
    assert audio.validate_wav(path) > 0


def test_repair_leaves_consistent_wav_untouched(make_wav, tmp_path):
    path = make_wav(tmp_path / "ok.wav")
    original = path.read_bytes()
    assert audio.repair_interrupted_wav_header(path) is True
    assert path.read_bytes() == original


def test_repair_rejects_foreign_format(tmp_path):
    path = tmp_path / "other.wav"
    path.write_bytes(b"RIFF" + (40).to_bytes(4, "little") + b"WAVE" + bytes(32))
    assert audio.repair_interrupted_wav_header(path) is False


def test_stop_escalates_and_closes_pipe():
    process = Mock(returncode=-9)
    process.poll.return_value = None
    process.wait.side_effect = [
        subprocess.TimeoutExpired("capture", 2),
        subprocess.TimeoutExpired("capture", 1),
        -9,
    ]
    assert audio.stop_audio_process(process) is False
    process.send_signal.assert_called_once()
    process.terminate.assert_called_once()
    process.kill.assert_called_once()
    assert process.wait.call_count == 3
    process.stderr.close.assert_called_once()


def test_stop_reports_sigint():
    process = Mock(returncode=130)
    process.poll.return_value = None
    process.wait.return_value = 130
    assert audio.stop_audio_process(process) is True


def test_recorder_without_arecord_reports_error(monkeypatch, tmp_path):
    monkeypatch.setattr(audio.shutil, "which", lambda _: None)
    with pytest.raises(audio.AudioError, match="arecord"):
        audio.Recorder(tmp_path / "a.wav").start()


def test_last_stderr_returns_final_line(tmp_path):
    recorder = audio.Recorder(tmp_path / "a.wav")
    recorder._stderr.extend(b"linha um\nlinha dois\n")
    assert recorder.last_stderr() == "linha dois"


def test_discard_removes_file(tmp_path):
    path = tmp_path / "a.wav"
    path.write_bytes(b"x")
    audio.Recorder(path).discard()
    assert not path.exists()
