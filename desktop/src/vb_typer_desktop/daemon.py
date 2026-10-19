"""Núcleo do ditado: atalho, gravação, job na API e inserção no ponto do cursor."""

from __future__ import annotations

import contextlib
import signal
import sys
import threading
import time

from vb_typer_desktop.api import ApiClient, ApiError, Job
from vb_typer_desktop.audio import (
    MAX_AUDIO_SECONDS,
    AudioError,
    Recorder,
    repair_interrupted_wav_header,
    validate_wav,
)
from vb_typer_desktop.geometry import Rect, indicator_rect
from vb_typer_desktop.hotkey import HotkeyState
from vb_typer_desktop.notify import notify as default_notify
from vb_typer_desktop.platform import Platform, get_platform
from vb_typer_desktop.preferences import Preferences
from vb_typer_desktop.ui import open_ui

POLL_INTERVAL_S = 0.3
JOB_TIMEOUT_S = 180.0
INSERTED_FLASH_S = 1.2
ERROR_FLASH_S = 3.0
INDICATOR_REFRESH_S = 0.25


class Cancelled(RuntimeError):
    """Cancelamento pedido pelo usuário: nada deve ser inserido."""


class Daemon:
    """Um job por vez: atalho → gravação → transcrição → inserção."""

    def __init__(
        self,
        api: ApiClient,
        platform: Platform | None = None,
        model: str = "",
        language: str = "",
        mode: str = "",
        notify_fn=None,
        open_ui_fn=None,
        preferences: Preferences | None = None,
        poll_interval: float = POLL_INTERVAL_S,
        job_timeout: float = JOB_TIMEOUT_S,
    ) -> None:
        self.api = api
        self.platform = platform or get_platform()
        self.model = model
        self.language = language
        self.preferences = preferences or Preferences()
        self._notify_fn = notify_fn or default_notify
        self._open_ui_fn = open_ui_fn or self._default_open_ui
        self.poll_interval = poll_interval
        self.job_timeout = job_timeout
        self.mode = mode
        self.state = HotkeyState()
        self.lock = threading.RLock()
        self.busy = False
        self.paused = False
        self.watcher = None
        self.recorder: Recorder | None = None
        self.target_window: int | None = None
        self.cancel = threading.Event()
        self.done = threading.Event()
        self.worker: threading.Thread | None = None
        self.capture_timer: threading.Timer | None = None
        self.last_transcript = ""
        self.quitting = False
        self._flash_until = 0.0
        self._flash_phase = "idle"
        self._flash_message = ""
        self._indicator_cache: tuple[float, str, Rect | None] = (0.0, "idle", None)

    # ------------------------------------------------------------------ estado

    @property
    def listening(self) -> bool:
        watcher = self.watcher
        return watcher is not None and bool(watcher.running)

    def _default_open_ui(self) -> bool:
        return open_ui(self.api.base_url)

    def _flash(self, phase: str, message: str, seconds: float) -> None:
        """Marca um estado passageiro (inserido/erro) para o indicador mostrar."""
        self._flash_phase = phase
        self._flash_message = message
        self._flash_until = time.monotonic() + seconds

    def _phase(self) -> str:
        if self.recorder is not None:
            return "recording"
        if self.busy:
            return "processing"
        if time.monotonic() < self._flash_until:
            return self._flash_phase
        return "idle"

    def _notify(self, title: str, message: str, urgency: str = "normal") -> None:
        """Rotina vai para o indicador visual; o balão do sistema fica para o resto."""
        if urgency == "critical":
            self._flash("error", message, ERROR_FLASH_S)
            if self.preferences.shows_error_balloons:
                self._notify_fn(title, message, urgency)
        elif self.preferences.shows_routine_balloons:
            self._notify_fn(title, message, urgency)

    def _cancel_timer(self) -> None:
        if self.capture_timer is not None:
            self.capture_timer.cancel()
            self.capture_timer = None

    def _indicator_box(self, phase: str) -> Rect | None:
        """Onde desenhar o indicador; leva em conta a fase e as preferências."""
        if phase == "idle" or not self.preferences.shows_indicator:
            return None
        now = time.monotonic()
        cached_at, cached_phase, cached_box = self._indicator_cache
        if cached_phase == phase and now - cached_at < INDICATOR_REFRESH_S:
            return cached_box
        anchor = self.preferences.anchor
        window = self.platform.window_rect(self.target_window) if anchor == "window" else None
        pointer = self.platform.pointer_position() if anchor == "pointer" else None
        box = indicator_rect(
            anchor,
            self.preferences.position,
            self.preferences.size,
            window=window,
            screen=self.platform.screen_rect(),
            pointer=pointer,
        )
        self._indicator_cache = (now, phase, box)
        return box

    def state_snapshot(self) -> dict:
        recording = self.recorder is not None
        phase = self._phase()
        snapshot = {
            "ok": True,
            "state": "recording" if recording else ("processing" if self.busy else "idle"),
            "dictating": self.listening,
            "recording": recording,
            "hidden": False,
            "phase": phase,
            "level": self.recorder.level if self.recorder is not None else 0,
        }
        if phase in ("inserted", "error") and self._flash_message:
            snapshot["message"] = self._flash_message
        box = self._indicator_box(phase)
        if box is not None:
            snapshot["indicator"] = {
                "x": box.x,
                "y": box.y,
                "w": box.width,
                "h": box.height,
            }
        return snapshot

    # ------------------------------------------------------------------ atalho

    def on_modifier(self, group: str, pressed: bool) -> None:
        """Chamado pelo observador de plataforma, na thread dele."""
        action = self.state.feed(group, pressed)
        if action == "start":
            self.start_recording()
        elif action == "stop":
            self.stop_recording()

    def start_listener(self) -> None:
        if self.busy:
            raise RuntimeError("Aguarde o trabalho anterior encerrar antes de reiniciar.")
        self.platform.ensure_session()
        self.paused = False
        self.cancel.clear()
        if self.listening:
            return
        self.state = HotkeyState()
        self.watcher = self.platform.hotkey_watcher(self.on_modifier)
        self.watcher.start()
        self._notify(
            "VB Typer ativo",
            "Segure Ctrl+Super para gravar; solte Ctrl ou Super para transcrever e inserir.",
        )

    def stop_listener(self) -> None:
        """Pausa o ditado: cancela o trabalho em curso e descarta o áudio local."""
        self.cancel.set()
        worker = None
        with self.lock:
            self.paused = True
            self._cancel_timer()
            watcher = self.watcher
            self.watcher = None
            recorder = self.recorder
            if recorder is not None:
                self.recorder = None
                self.busy = True
                worker = threading.Thread(
                    target=self._discard_capture, args=(recorder,), daemon=True
                )
                # Guardado em `self.worker` para o encerramento esperar a captura terminar.
                self.worker = worker
        # Nunca parar o observador sob o lock: o callback dele toma o mesmo lock.
        if watcher is not None:
            watcher.stop()
        if worker is not None:
            worker.start()
        self._notify("VB Typer", "Ditado pausado; trabalho cancelado.")

    def toggle_listener(self) -> None:
        if self.listening:
            self.stop_listener()
            return
        self.start_listener()

    # --------------------------------------------------------------- gravação

    def start_recording(self) -> None:
        with self.lock:
            if self.paused or self.busy or self.recorder is not None:
                return
            self.cancel.clear()
            target = self.platform.active_window()
            if target is None:
                self._notify(
                    "VB Typer", "Não consegui identificar a janela de destino X11.", "critical"
                )
                return
            recorder = Recorder()
            try:
                recorder.start()
            except AudioError as exc:
                recorder.discard()
                self._notify("VB Typer", str(exc), "critical")
                return
            self.recorder = recorder
            self.target_window = target
            self.capture_timer = threading.Timer(MAX_AUDIO_SECONDS, self.stop_recording)
            self.capture_timer.daemon = True
            self.capture_timer.start()
        self._notify("VB Typer", "Gravando. Solte Ctrl ou Super para transcrever.")

    def stop_recording(self) -> None:
        """Solta do atalho ou limite de tempo: entrega o áudio para transcrição."""
        with self.lock:
            recorder = self.recorder
            if recorder is None:
                return
            self.recorder = None
            self.busy = True
            self._cancel_timer()
            target = self.target_window
            self.worker = threading.Thread(
                target=self._finish_and_transcribe, args=(recorder, target), daemon=True
            )
        self.worker.start()

    def _discard_capture(self, recorder: Recorder) -> None:
        try:
            recorder.stop()
        finally:
            recorder.discard()
            with self.lock:
                self.busy = False

    def _finish_and_transcribe(self, recorder: Recorder, target: int | None) -> None:
        path = recorder.path
        try:
            interrupted = recorder.stop()
            if self.cancel.is_set():
                return
            repaired = False
            if interrupted:
                repaired = repair_interrupted_wav_header(path)
            returncode = recorder.returncode
            if returncode not in (0, -signal.SIGINT, 130) and not (
                returncode == 1 and interrupted and repaired
            ):
                detail = recorder.last_stderr()
                suffix = f" {detail}" if detail else ""
                raise AudioError(f"Gravador de áudio falhou (código {returncode}).{suffix}")
            validate_wav(path, recorder.elapsed)
            if self.cancel.is_set():
                return
            self._notify("VB Typer", "Áudio gravado. Transcrevendo…")
            job = self._wait_for_terminal(self._submit(path))
            if job is None:
                return
            self._insert(job, target)
        except Cancelled:
            pass
        except Exception as exc:
            if not self.cancel.is_set():
                self._notify("VB Typer — erro", str(exc), "critical")
        finally:
            path.unlink(missing_ok=True)
            with self.lock:
                self.busy = False

    # ------------------------------------------------------------ transcrição

    def _options(self) -> tuple[str | None, str, str | None]:
        """Modelo, idioma e modo vigentes na interface; a falha não impede o ditado."""
        model, language, mode = self.api.current_options()
        return (
            model or self.model or None,
            language or self.language or "pt",
            mode or self.mode or None,
        )

    def _submit(self, path) -> Job:
        model, language, mode = self._options()
        return self.api.create_job(
            path.read_bytes(),
            filename=path.name,
            content_type="audio/wav",
            model=model,
            language=language,
            mode=mode,
        )

    def _wait_for_terminal(self, job: Job) -> Job | None:
        deadline = time.monotonic() + self.job_timeout
        while True:
            if self.cancel.is_set():
                self._request_cancel(job)
                return None
            if job.finished:
                return job
            if time.monotonic() >= deadline:
                self._request_cancel(job)
                raise RuntimeError("Tempo limite de transcrição excedido.")
            self.cancel.wait(self.poll_interval)
            job = self.api.get_job(job.id)

    def _request_cancel(self, job: Job) -> None:
        with contextlib.suppress(ApiError):
            self.api.cancel_job(job.id)

    def _insert(self, job: Job, target: int | None) -> None:
        if job.status != "succeeded":
            raise RuntimeError(job.error or "A transcrição falhou.")
        text = (job.text or "").strip()
        if not text:
            raise RuntimeError("A API não reconheceu fala nesse áudio.")
        self.last_transcript = text
        if self.cancel.is_set():
            return
        started = time.monotonic()
        self.platform.type_text(text, target, self.cancel)
        self._mark_inserted(job, int((time.monotonic() - started) * 1000))
        self._flash("inserted", "inserido", INSERTED_FLASH_S)
        self._notify("VB Typer", "Transcrição inserida no aplicativo que estava em foco.")

    def _mark_inserted(self, job: Job, insert_ms: int) -> None:
        """O histórico é informativo: uma falha aqui não invalida a inserção."""
        if job.transcription_id is None:
            return
        try:
            self.api.mark_inserted(job.transcription_id, True, insert_ms)
        except ApiError as exc:
            print(f"Falha ao registrar a inserção no histórico: {exc}", file=sys.stderr, flush=True)

    # -------------------------------------------------------------- ciclo de vida

    def control_command(self, command: str) -> dict:
        """Comandos da bandeja; nunca bloqueiam a thread do socket."""
        if command == "state":
            return self.state_snapshot()
        actions = {"show": self.show_ui, "toggle": self.toggle_listener, "quit": self.shutdown}
        action = actions.get(command)
        if action is None:
            return {"ok": False}
        threading.Thread(target=action, daemon=True).start()
        return {"ok": True}

    def show_ui(self) -> bool:
        try:
            return bool(self._open_ui_fn())
        except Exception:
            return False

    def wait(self) -> None:
        """Bloqueia até o encerramento ser pedido (ou até Ctrl+C)."""
        self.done.wait()

    def shutdown(self) -> None:
        self.quitting = True
        if self.listening or self.recorder is not None:
            self.stop_listener()
        else:
            self.cancel.set()
            with self.lock:
                self.paused = True
        worker = self.worker
        if worker is not None and worker.is_alive():
            worker.join(timeout=5)
        self.done.set()
