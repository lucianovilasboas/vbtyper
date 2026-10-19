"""Dublês dos testes: nem API real, nem sessão gráfica real."""

from __future__ import annotations

from pathlib import Path

from vb_typer_desktop.api import Job


class FakeWatcher:
    """Observador de atalho controlado pelo teste."""

    def __init__(self, on_change) -> None:
        self.on_change = on_change
        self.running = False

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False

    def press(self, group: str) -> None:
        self.on_change(group, True)

    def release(self, group: str) -> None:
        self.on_change(group, False)


class FakePlatform:
    """Adaptador de plataforma que registra o que seria digitado."""

    name = "fake"

    def __init__(
        self,
        window: int | None = 7,
        type_failure: Exception | None = None,
        session_failure: Exception | None = None,
    ) -> None:
        self.window = window
        self.type_failure = type_failure
        self.session_failure = session_failure
        self.typed: list[str] = []
        self.targets: list[int | None] = []
        self.watcher: FakeWatcher | None = None

    def ensure_session(self) -> None:
        if self.session_failure is not None:
            raise self.session_failure

    def active_window(self) -> int | None:
        return self.window

    def type_text(self, text: str, target: int | None, cancel=None) -> None:
        if self.type_failure is not None:
            raise self.type_failure
        if cancel is not None and cancel.is_set():
            raise RuntimeError("cancelado antes de inserir")
        self.typed.append(text)
        self.targets.append(target)

    def hotkey_watcher(self, on_change) -> FakeWatcher:
        self.watcher = FakeWatcher(on_change)
        return self.watcher


class FakeApi:
    """Cliente da API em memória, sem rede."""

    base_url = "http://127.0.0.1:8765"

    def __init__(
        self,
        text: str = "Ola, acao!",
        status: str = "succeeded",
        error: str | None = None,
        transcription_id: int | None = 42,
        model: str = "gpt-4o-mini-transcribe",
        language: str = "pt",
    ) -> None:
        self.text = text
        self.status = status
        self.error = error
        self.transcription_id = transcription_id
        self.model = model
        self.language = language
        self.uploads: list[dict] = []
        self.polls = 0
        self.cancelled: list[str] = []
        self.inserts: list[tuple[int, bool, int | None]] = []
        self.on_poll = None

    def ready(self) -> dict:
        return {"status": "ok", "database": True, "api_key_configured": True}

    def settings(self) -> dict:
        return {"model": self.model, "language": self.language}

    def current_model_language(self) -> tuple[str, str]:
        return self.model, self.language

    def create_job(self, data, filename, content_type, model=None, language=None) -> Job:
        self.uploads.append(
            {
                "bytes": len(data),
                "filename": filename,
                "content_type": content_type,
                "model": model,
                "language": language,
            }
        )
        return Job(id="job-1", status="queued")

    def get_job(self, job_id: str) -> Job:
        self.polls += 1
        if self.on_poll is not None:
            self.on_poll()
        return Job(
            id=job_id,
            status=self.status,
            error=self.error,
            transcription_id=self.transcription_id,
            text=self.text,
        )

    def cancel_job(self, job_id: str) -> Job:
        self.cancelled.append(job_id)
        return Job(id=job_id, status="canceled")

    def mark_inserted(self, transcription_id: int, inserted: bool, insert_ms=None) -> None:
        self.inserts.append((transcription_id, inserted, insert_ms))

    def close(self) -> None:
        return None


class FakeRecorder:
    """Captura já concluída, pronta para o caminho de transcrição."""

    def __init__(
        self,
        path: Path,
        elapsed: float = 1.0,
        returncode: int = 0,
        interrupted: bool = False,
        stderr: str = "",
    ) -> None:
        self.path = Path(path)
        self.elapsed = elapsed
        self.returncode = returncode
        self.interrupted = interrupted
        self.stderr = stderr
        self.discarded = False

    def stop(self) -> bool:
        return self.interrupted

    def last_stderr(self) -> str:
        return self.stderr

    def discard(self) -> None:
        self.discarded = True
        self.path.unlink(missing_ok=True)
