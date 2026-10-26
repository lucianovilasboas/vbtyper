"""Dublês dos testes: nem API real, nem sessão gráfica real."""

from __future__ import annotations

from pathlib import Path

from vb_typer_desktop.api import Job
from vb_typer_desktop.geometry import Rect
from vb_typer_desktop.profile_switch import DEFAULT_HOTKEYS

# Áreas padrão dos dublês: uma janela qualquer dentro de uma tela 1920x1080.
DEFAULT_WINDOW_AREA = Rect(100, 200, 900, 600)
DEFAULT_SCREEN_AREA = Rect(0, 0, 1920, 1080)


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
        window_area: Rect | None = DEFAULT_WINDOW_AREA,
        screen_area: Rect | None = DEFAULT_SCREEN_AREA,
        pointer: tuple[int, int] | None = (500, 500),
    ) -> None:
        self.window = window
        self.type_failure = type_failure
        self.session_failure = session_failure
        self.window_area = window_area
        self.screen_area = screen_area
        self.pointer = pointer
        self.typed: list[str] = []
        self.targets: list[int | None] = []
        self.watcher: FakeWatcher | None = None
        self.combo_watchers: list[FakeComboWatcher] = []

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

    def combo_watcher(self, bindings, on_action, on_error=None) -> FakeComboWatcher:
        watcher = FakeComboWatcher(bindings, on_action, on_error)
        self.combo_watchers.append(watcher)
        return watcher

    @property
    def combos(self) -> FakeComboWatcher:
        return self.combo_watchers[-1]

    def window_rect(self, window: int | None) -> Rect | None:
        return self.window_area if window is not None else None

    def screen_rect(self) -> Rect | None:
        return self.screen_area

    def pointer_position(self) -> tuple[int, int] | None:
        return self.pointer


class FakeComboWatcher:
    """Observador das combinações de perfil, disparado pelo teste."""

    def __init__(self, bindings, on_action, on_error=None) -> None:
        self.bindings = bindings
        self.on_action = on_action
        self.on_error = on_error
        self.running = False
        self.starts = 0

    def start(self) -> None:
        self.starts += 1
        self.running = True

    def stop(self) -> None:
        self.running = False

    def fire(self, action: str) -> None:
        self.on_action(action)

    def fail(self, message: str) -> None:
        if self.on_error is not None:
            self.on_error(message)


class FakeApi:
    """Cliente da API em memória, sem rede."""

    base_url = "http://127.0.0.1:8765"
    DEFAULT_PROFILES = [
        {"slug": "literal", "name": "Transcrição fiel"},
        {"slug": "revisado", "name": "Texto revisado"},
        {"slug": "email", "name": "E-mail profissional"},
    ]

    def __init__(
        self,
        text: str = "Ola, acao!",
        status: str = "succeeded",
        error: str | None = None,
        transcription_id: int | None = 42,
        model: str = "gpt-4o-mini-transcribe",
        language: str = "pt",
        mode: str = "literal",
        default_profile: str = "literal",
        profiles: list[dict] | None = None,
        phase: str = "",
        hotkeys: dict[str, str] | None = None,
        delivery: str = "text",
        tools: tuple[str, ...] = (),
    ) -> None:
        self.mode = mode
        self.phase = phase
        self.delivery = delivery
        self.tools = tuple(tools)
        self.default_profile = default_profile
        self.profiles = list(profiles) if profiles is not None else list(self.DEFAULT_PROFILES)
        self.hotkeys = dict(hotkeys) if hotkeys is not None else dict(DEFAULT_HOTKEYS)
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
        self.patched: list[dict] = []
        self.on_poll = None

    def ready(self) -> dict:
        return {"status": "ok", "database": True, "api_key_configured": True}

    def settings(self) -> dict:
        return {
            "model": self.model,
            "language": self.language,
            "mode": self.mode,
            "default_profile": self.default_profile,
            "hotkeys": dict(self.hotkeys),
        }

    def settings_or_empty(self) -> dict:
        return self.settings()

    def current_options(self) -> tuple[str, str, str, str]:
        return self.model, self.language, self.mode, self.default_profile

    def list_profiles(self) -> list[dict]:
        return list(self.profiles)

    def patch_settings(self, changes: dict) -> dict:
        self.patched.append(changes)
        if "mode" in changes:
            self.mode = str(changes["mode"])
            self.default_profile = "literal" if self.mode == "literal" else "revisado"
        if "default_profile" in changes:
            self.default_profile = str(changes["default_profile"])
            self.mode = "literal" if self.default_profile == "literal" else "smart"
        return {"mode": self.mode, "default_profile": self.default_profile}

    def create_job(
        self, data, filename, content_type, model=None, language=None, mode=None, profile=None
    ) -> Job:
        self.uploads.append(
            {
                "bytes": len(data),
                "filename": filename,
                "content_type": content_type,
                "model": model,
                "language": language,
                "mode": mode,
                "profile": profile,
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
            phase=self.phase,
            delivery=self.delivery,
            tools=self.tools,
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
        self.level = 0
        self.waveform_data = [0, 64, 128, 192, 255]
        self.discarded = False

    def waveform(self) -> list[int]:
        return list(self.waveform_data)

    def stop(self) -> bool:
        return self.interrupted

    def last_stderr(self) -> str:
        return self.stderr

    def discard(self) -> None:
        self.discarded = True
        self.path.unlink(missing_ok=True)
