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
from vb_typer_desktop.profile_switch import (
    DEFAULT_HOTKEYS,
    PROFILE_DEFAULT,
    STEPS,
    bindings,
    next_profile,
)
from vb_typer_desktop.ui import open_ui

POLL_INTERVAL_S = 0.3
JOB_TIMEOUT_S = 180.0
# De quanto em quanto tempo relemos a configuração, para a bandeja ficar em
# sincronia com o que for mudado na interface.
OPTIONS_REFRESH_S = 10.0
# Quanto tempo a pílula do perfil fica no indicador depois do atalho.
PROFILE_FLASH_S = 1.2
# Aviso de que o ditado repetia o que já estava escrito (nada é inserido).
NOTHING_FLASH_S = 2.0
MODES = ("literal", "smart")
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
        self.mode_current = ""
        self.profile_current = ""
        # Troca temporária por atalho: não altera o padrão do backend.
        self.profile_override = ""
        self.hotkeys: dict[str, str] = dict(DEFAULT_HOTKEYS)
        self.combo_watcher = None
        self._combo_warned = ""
        self.profiles: list[dict] = []
        self.job_phase = ""
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
    def current_mode(self) -> str:
        """Modo de transcrição vigente (o literal é o padrão)."""
        return self.mode_current or self.mode or "literal"

    @property
    def current_profile(self) -> str:
        """Perfil que o próximo ditado vai usar (a troca por atalho manda)."""
        return self.profile_override or self.profile_current

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
            "mode": self.current_mode,
            "profile": self.current_profile,
            "profiles": self.profiles,
            "job_phase": self.job_phase,
        }
        if recording and self.preferences.shows_indicator and self.preferences.shape == "wave":
            get_waveform = getattr(self.recorder, "waveform", None)
            if callable(get_waveform):
                snapshot["waveform"] = get_waveform()
        if phase in ("inserted", "error", "profile", "nothing") and self._flash_message:
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
        self._start_combo_watcher()
        self._start_options_watcher()
        self._notify(
            "VB Typer ativo",
            "Segure Ctrl+Super para gravar; solte Ctrl ou Super para transcrever e inserir. "
            "Os atalhos de perfil estão em Configurações › Atalhos.",
        )

    def _start_options_watcher(self) -> None:
        """Lê a configuração de tempos em tempos, para a bandeja não ficar velha."""
        if getattr(self, "_options_thread", None) is not None:
            return
        thread = threading.Thread(target=self._watch_options, name="vb-typer-options", daemon=True)
        self._options_thread = thread
        thread.start()

    def _watch_options(self) -> None:
        while not self.done.is_set():
            self.refresh_options()
            self.done.wait(OPTIONS_REFRESH_S)

    def refresh_options(self) -> None:
        """Relê modelo, idioma, perfil e atalhos (a bandeja acompanha sem reiniciar).

        Uma falha da API mantém o que já estava em uso — inclusive a lista de
        perfis, para o menu da bandeja não esvaziar enquanto o servidor volta.
        """
        payload = self.api.settings_or_empty()
        profiles = self.api.list_profiles()
        model = str(payload.get("model") or "")
        language = str(payload.get("language") or "")
        mode = str(payload.get("mode") or "")
        profile = str(payload.get("default_profile") or "")
        if model:
            self.model = model
        if language:
            self.language = language
        if mode:
            self.mode_current = mode
        if profiles:
            self.profiles = profiles
            slugs = {item["slug"] for item in profiles}
            if self.profile_override and self.profile_override not in slugs:
                # Perfil apagado na interface: a troca temporária perde o sentido.
                self.profile_override = ""
            if profile and profile not in slugs:
                # Perfil apagado na interface enquanto o cliente rodava.
                profile = "literal" if "literal" in slugs else ""
        if profile:
            self.profile_current = profile
        hotkeys = payload.get("hotkeys")
        if isinstance(hotkeys, dict) and hotkeys:
            self._apply_hotkeys({str(key): str(value) for key, value in hotkeys.items()})

    def set_mode(self, value: str) -> bool:
        """Troca o modo de transcrição no backend (é ele que guarda a escolha)."""
        if value not in MODES:
            return False
        try:
            payload = self.api.patch_settings({"mode": value})
        except ApiError as exc:
            self._notify("VB Typer — erro", str(exc), "critical")
            return False
        self.mode_current = str(payload.get("mode") or value)
        # Cliente antigo trocando modo: o perfil acompanha (smart = revisado).
        default_profile = str(payload.get("default_profile") or "")
        if default_profile:
            self.profile_current = default_profile
        return True

    def set_profile(self, slug: str) -> bool:
        """Troca o perfil de texto no backend (é ele que guarda a escolha)."""
        slugs = {item["slug"] for item in self.profiles}
        if not slug or (slugs and slug not in slugs):
            return False
        try:
            payload = self.api.patch_settings({"default_profile": slug})
        except ApiError as exc:
            self._notify("VB Typer — erro", str(exc), "critical")
            return False
        self.profile_current = str(payload.get("default_profile") or slug)
        # Escolha explícita (bandeja): o ciclo temporário perde a razão de ser.
        self.profile_override = ""
        mode = str(payload.get("mode") or "")
        if mode:
            self.mode_current = mode
        return True

    # -------------------------------------------------------- atalhos de perfil

    def profile_name(self, slug: str) -> str:
        for item in self.profiles:
            if item.get("slug") == slug:
                return str(item.get("name") or slug)
        return slug

    def cycle_profile(self, step: int = 1) -> bool:
        """Passa para o próximo perfil sem mexer no padrão gravado no backend."""
        if not step:
            return False
        with self.lock:
            if self.recorder is not None or self.busy:
                return False
            slugs = [str(item.get("slug") or "") for item in self.profiles]
            slugs = [slug for slug in slugs if slug]
            if not slugs:
                return False
            base = self.profile_override or self.profile_current or slugs[0]
            self.profile_override = next_profile(slugs, base, step)
            position = slugs.index(self.profile_override) + 1
            name = self.profile_name(self.profile_override)
            self._flash("profile", f"{name} ({position}/{len(slugs)})", PROFILE_FLASH_S)
        return True

    def reset_profile(self) -> bool:
        """Volta ao perfil padrão configurado, descartando o ciclo."""
        with self.lock:
            if self.recorder is not None or self.busy:
                return False
            name = self.profile_name(self.profile_current) if self.profile_current else "padrão"
            self.profile_override = ""
            self._flash("profile", f"{name} (padrão)", PROFILE_FLASH_S)
        return True

    def on_combo(self, action: str) -> None:
        """Chamado pelo observador de combinações, na thread dele."""
        if action == PROFILE_DEFAULT:
            self.reset_profile()
        else:
            self.cycle_profile(STEPS.get(action, 0))

    def _apply_hotkeys(self, hotkeys: dict[str, str]) -> None:
        """Adota as combinações da interface; se mudaram, re-arma o grab."""
        if bindings(hotkeys) == bindings(self.hotkeys):
            return
        self.hotkeys = dict(hotkeys)
        self._restart_combo_watcher()

    def _start_combo_watcher(self) -> None:
        factory = getattr(self.platform, "combo_watcher", None)
        parsed = bindings(self.hotkeys)
        if factory is None or not parsed:
            return
        try:
            watcher = factory(parsed, self.on_combo, self._combo_failed)
        except Exception as exc:  # plataforma sem a capacidade, por exemplo
            self._combo_failed(str(exc))
            return
        self.combo_watcher = watcher
        watcher.start()

    def _restart_combo_watcher(self) -> None:
        watcher = self.combo_watcher
        self.combo_watcher = None
        # Parar fora do lock: o callback do observador toma o mesmo lock.
        if watcher is not None:
            watcher.stop()
        if self.listening:
            self._start_combo_watcher()

    def _combo_failed(self, message: str) -> None:
        """Avisa uma vez: um atalho ocupado não pode virar enxurrada de erros."""
        if self._combo_warned == message:
            return
        self._combo_warned = message
        self._notify(
            "VB Typer — atalhos",
            f"Troca de perfil por atalho indisponível: {message}.",
            "critical",
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
            combos = self.combo_watcher
            self.combo_watcher = None
            recorder = self.recorder
            if recorder is not None:
                self.recorder = None
                self.busy = True
                worker = threading.Thread(
                    target=self._discard_capture, args=(recorder,), daemon=True
                )
                # Guardado em `self.worker` para o encerramento esperar a captura terminar.
                self.worker = worker
        # Nunca parar os observadores sob o lock: os callbacks deles tomam o mesmo lock.
        if watcher is not None:
            watcher.stop()
        if combos is not None:
            combos.stop()
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
                self.job_phase = ""

    # ------------------------------------------------------------ transcrição

    def _options(self) -> tuple[str | None, str, str]:
        """Modelo, idioma e perfil vigentes; a falha não impede o ditado."""
        model, language, _mode, profile = self.api.current_options()
        return (
            model or self.model or None,
            language or self.language or "pt",
            self.profile_override or profile or self.profile_current or "",
        )

    def _submit(self, path) -> Job:
        model, language, profile = self._options()
        self.job_phase = ""
        return self.api.create_job(
            path.read_bytes(),
            filename=path.name,
            content_type="audio/wav",
            model=model,
            language=language,
            profile=profile or None,
        )

    def _wait_for_terminal(self, job: Job) -> Job | None:
        deadline = time.monotonic() + self.job_timeout
        self.job_phase = job.phase
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
            self.job_phase = job.phase

    def _request_cancel(self, job: Job) -> None:
        with contextlib.suppress(ApiError):
            self.api.cancel_job(job.id)

    def _insert(self, job: Job, target: int | None) -> None:
        if job.status != "succeeded":
            raise RuntimeError(job.error or "A transcrição falhou.")
        text = (job.text or "").strip()
        if not text:
            # Perfil contínuo com tudo já escrito: o job conclui sem texto e não há
            # nada a inserir. Isso é sucesso, não erro de reconhecimento.
            self._flash("nothing", "nada a acrescentar", NOTHING_FLASH_S)
            self._notify(
                "VB Typer", "Nada a acrescentar: o ditado repetia o que já estava escrito."
            )
            return
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

    def control_command(self, command: str, value: str | None = None) -> dict:
        """Comandos da bandeja; nunca bloqueiam a thread do socket."""
        if command == "state":
            return self.state_snapshot()
        if command == "mode":
            return {"ok": self.set_mode(value or "")}
        if command == "profile":
            return {"ok": self.set_profile(value or "")}
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
