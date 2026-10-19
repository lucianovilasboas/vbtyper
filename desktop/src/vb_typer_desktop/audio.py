"""Captura do microfone e validação do WAV (porte do app 1.x)."""

from __future__ import annotations

import os
import shutil
import signal
import struct
import subprocess
import tempfile
import threading
import time
from pathlib import Path

MAX_AUDIO_SECONDS = 120
MAX_AUDIO_BYTES = MAX_AUDIO_SECONDS * 32000 + 4096
MAX_STDERR_BYTES = 4096
PCM_FORMAT = (1, 1, 16000, 32000, 2, 16)


class AudioError(RuntimeError):
    """Falha de captura ou áudio gravado inválido."""


def temp_wav_path() -> Path:
    handle, name = tempfile.mkstemp(prefix="vb-typer-", suffix=".wav")
    os.close(handle)
    return Path(name)


def capture_command(path: Path) -> list[str]:
    """Comando do ``arecord``: mono, 16 kHz, 16 bits, WAV, até 120 s."""
    return [
        "arecord",
        "-D",
        "pulse",
        "-f",
        "S16_LE",
        "-r",
        "16000",
        "-c",
        "1",
        "-t",
        "wav",
        "-d",
        str(MAX_AUDIO_SECONDS),
        str(path),
    ]


def validate_wav(path: Path, elapsed: float | None = None) -> float:
    """Valida todos os chunks RIFF, o formato PCM exato, o tamanho e a duração."""
    if not path.is_file() or not 44 <= path.stat().st_size <= MAX_AUDIO_BYTES:
        raise AudioError("WAV vazio ou excedeu o limite de 120 segundos.")
    data = path.read_bytes()
    if (
        data[:4] != b"RIFF"
        or data[8:12] != b"WAVE"
        or struct.unpack_from("<I", data, 4)[0] != len(data) - 8
    ):
        raise AudioError("Estrutura RIFF inválida.")
    offset, fmt, pcm_size = 12, None, None
    while offset + 8 <= len(data):
        name, size = struct.unpack_from("<4sI", data, offset)
        start = offset + 8
        end = start + size
        if end > len(data):
            raise AudioError("Chunk WAV truncado.")
        if name == b"fmt ":
            if size != 16 or fmt is not None:
                raise AudioError("Formato WAV inválido.")
            fmt = struct.unpack_from("<HHIIHH", data, start)
        elif name == b"data":
            if pcm_size is not None:
                raise AudioError("Dados WAV duplicados.")
            pcm_size = size
        offset = end + (size & 1)
    if offset != len(data) or fmt != PCM_FORMAT or pcm_size is None or pcm_size % 2:
        raise AudioError("Formato PCM WAV inválido.")
    duration = pcm_size / 32000
    if not 0.15 <= duration <= MAX_AUDIO_SECONDS or (
        elapsed is not None and duration > elapsed + 1
    ):
        raise AudioError("Duração WAV inválida (mínimo 0,15 s; máximo 120 s).")
    return duration


def repair_interrupted_wav_header(path: Path) -> bool:
    """Conserta os tamanhos RIFF/data após o SIGINT, só para o PCM esperado."""
    try:
        if path.stat().st_size > MAX_AUDIO_BYTES:
            return False
        wav = bytearray(path.read_bytes())
        if len(wav) < 44 or wav[:4] != b"RIFF" or wav[8:12] != b"WAVE":
            return False
        offset = 12
        pcm_format = None
        while offset + 8 <= len(wav):
            chunk_id = bytes(wav[offset : offset + 4])
            chunk_size = struct.unpack_from("<I", wav, offset + 4)[0]
            content_start = offset + 8
            if chunk_id == b"fmt ":
                if chunk_size < 16 or content_start + 16 > len(wav):
                    return False
                pcm_format = struct.unpack_from("<HHIIHH", wav, content_start)
            elif chunk_id == b"data":
                if pcm_format != PCM_FORMAT:
                    return False
                # O SIGINT pode deixar tanto o marcador 0x80000000 (sem -d) quanto
                # a duração prevista inteira (arecord -d 120) nos tamanhos.
                data_size = len(wav) - content_start
                if data_size <= 0 or data_size % 2 or len(wav) > 0xFFFFFFFF:
                    return False
                declared_data = chunk_size
                declared_riff = struct.unpack_from("<I", wav, 4)[0]
                if data_size == declared_data and len(wav) - 8 == declared_riff:
                    return True  # Já consistente; nada a reparar.
                if content_start + declared_data < len(wav):
                    return False  # Bytes sobrando: não é captura truncada.
                struct.pack_into("<I", wav, 4, len(wav) - 8)
                struct.pack_into("<I", wav, offset + 4, data_size)
                path.write_bytes(wav)
                return True
            next_offset = content_start + chunk_size + (chunk_size & 1)
            if next_offset > len(wav):
                return False
            offset = next_offset
        return False
    except (OSError, struct.error):
        return False


def stop_audio_process(process) -> bool:
    """Encerra a captura e fecha o pipe; devolve se o SIGINT foi enviado."""
    interrupted = False
    try:
        if process.poll() is None:
            try:
                process.send_signal(signal.SIGINT)
                interrupted = True
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            interrupted = False
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        return interrupted
    finally:
        if getattr(process, "stderr", None) is not None:
            process.stderr.close()


class Recorder:
    """Gravação em andamento: processo ``arecord``, dreno de stderr e duração."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else temp_wav_path()
        self.process: subprocess.Popen[bytes] | None = None
        self.started_at = time.monotonic()
        self.returncode: int | None = None
        self.interrupted = False
        self._stderr = bytearray()
        self._reader: threading.Thread | None = None

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    def start(self) -> None:
        recorder = shutil.which("arecord")
        if not recorder:
            raise AudioError("arecord não está instalado; não foi possível gravar.")
        command = capture_command(self.path)
        command[0] = recorder
        try:
            self.process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            raise AudioError(f"Não foi possível iniciar o microfone: {exc}") from exc
        self._reader = threading.Thread(
            target=self._drain_stderr, args=(self.process,), daemon=True
        )
        self._reader.start()

    def _drain_stderr(self, process: subprocess.Popen[bytes]) -> None:
        """Drena o stderr para o pipe não encher e travar o ``arecord``."""
        stream = process.stderr
        if stream is None:
            return
        try:
            while True:
                chunk = os.read(stream.fileno(), 256)
                if not chunk:
                    break
                self._stderr.extend(chunk)
                del self._stderr[:-MAX_STDERR_BYTES]
        except (OSError, ValueError):
            pass

    def last_stderr(self) -> str:
        text = self._stderr.decode("utf-8", "replace")
        lines = [line.strip() for line in text.replace("\r", "\n").split("\n") if line.strip()]
        return lines[-1] if lines else ""

    def stop(self) -> bool:
        """Encerra a captura; devolve ``True`` quando o SIGINT foi enviado."""
        process = self.process
        if process is None:
            return False
        self.interrupted = stop_audio_process(process)
        if self._reader is not None:
            self._reader.join(timeout=2)
        self.returncode = process.returncode
        return self.interrupted

    def discard(self) -> None:
        """Apaga o arquivo temporário sem enviar nada."""
        self.path.unlink(missing_ok=True)
