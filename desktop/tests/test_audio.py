"""Áudio: validação do WAV, reparo do RIFF e encerramento do arecord."""

from __future__ import annotations

import struct
import subprocess
from pathlib import Path
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


def test_last_stderr_ignores_the_level_meter(tmp_path):
    """O medidor ``-V mono`` polui o stderr; ele não é uma mensagem de erro."""
    recorder = audio.Recorder(tmp_path / "a.wav")
    recorder._stderr.extend(b"device busy\n  50%|#####     |\n 100%|##########|\n")
    assert recorder.last_stderr() == "device busy"


def test_last_stderr_ignores_the_arecord_banner(tmp_path):
    recorder = audio.Recorder(tmp_path / "a.wav")
    recorder._stderr.extend(
        b"Gravando WAVE '/tmp/x.wav' : Signed 16 bit Little Endian, Taxa 16000 Hz, Mono\n"
    )
    assert recorder.last_stderr() == ""


def test_capture_asks_for_the_level_meter():
    command = audio.capture_command(Path("/tmp/x.wav"))
    assert "-V" in command and command[command.index("-V") + 1] == "mono"


def test_capture_uses_a_short_period_for_a_live_level():
    """O período define a resolução do medidor: o padrão dava só ~7 por segundo."""
    command = audio.capture_command(Path("/tmp/x.wav"))
    assert "--period-size" in command
    frames = int(command[command.index("--period-size") + 1])
    assert frames <= 512  # 32 ms a 16 kHz
    assert 16000 / frames >= 30  # pelo menos 30 atualizações por segundo


def test_level_follows_the_arecord_meter(tmp_path):
    recorder = audio.Recorder(tmp_path / "a.wav")
    recorder._update_level(b"  10%|#   |")
    assert recorder.level == 10
    recorder._update_level(b"  87%|#####|")
    assert recorder.level == 87


def test_level_never_exceeds_one_hundred(tmp_path):
    recorder = audio.Recorder(tmp_path / "a.wav")
    recorder._update_level(b"999%|####|")
    assert recorder.level == 100


def test_level_stays_when_the_chunk_has_no_meter(tmp_path):
    recorder = audio.Recorder(tmp_path / "a.wav")
    recorder._update_level(b"  64%|####|")
    recorder._update_level("pulse: conexão perdida".encode())
    assert recorder.level == 64


def test_discard_removes_file(tmp_path):
    path = tmp_path / "a.wav"
    path.write_bytes(b"x")
    audio.Recorder(path).discard()
    assert not path.exists()


# ------------------------------------------------------------------- onda


def test_waveform_from_pcm_maps_to_the_web_scale():
    pcm = b"".join(struct.pack("<h", value) for value in (-32768, 0, 32767))
    points = audio.waveform_from_pcm(pcm, points=3)
    assert len(points) == 3
    assert points[0] == 0
    assert 127 <= points[1] <= 128
    assert points[2] == 255


def test_waveform_from_pcm_needs_two_samples():
    assert audio.waveform_from_pcm(b"") == []
    assert audio.waveform_from_pcm(b"\x00") == []
    assert audio.waveform_from_pcm(b"\x00\x00") == []


def test_waveform_from_pcm_caps_the_window_and_the_points():
    pcm = struct.pack("<h", 1000) * (audio.WAVEFORM_WINDOW_SAMPLES + 100)
    points = audio.waveform_from_pcm(pcm)
    assert len(points) == audio.WAVEFORM_POINTS
    assert audio.WAVEFORM_WINDOW_SAMPLES == 512


def test_recorder_waveform_reads_the_tail_of_the_capture(make_wav, tmp_path):
    path = make_wav(tmp_path / "captura.wav", seconds=0.2)
    assert len(audio.Recorder(path).waveform()) == audio.WAVEFORM_POINTS


def test_recorder_waveform_is_empty_before_the_header(make_wav, tmp_path):
    path = make_wav(tmp_path / "captura.wav", seconds=0.001)
    path.write_bytes(path.read_bytes()[:44])
    assert audio.Recorder(path).waveform() == []


def test_recorder_waveform_tolerates_a_missing_file(tmp_path):
    assert audio.Recorder(tmp_path / "nada.wav").waveform() == []
