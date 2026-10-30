"""Ciclo do ditado: atalho, gravação, transcrição, cancelamento e inserção."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from fakes import FakeApi, FakePlatform, FakeRecorder
from vb_typer_desktop import daemon as daemon_module
from vb_typer_desktop import preferences
from vb_typer_desktop.api import Job
from vb_typer_desktop.daemon import POLL_MAX_INTERVAL_S, Daemon
from vb_typer_desktop.preferences import Preferences


def build(api=None, platform=None, **kwargs):
    notifications: list[tuple[str, str, str]] = []

    def notify(title: str, message: str, urgency: str = "normal") -> None:
        notifications.append((title, message, urgency))

    kwargs.setdefault("poll_interval", 0.0)
    agent = Daemon(
        api=api or FakeApi(),
        platform=platform or FakePlatform(),
        notify_fn=notify,
        **kwargs,
    )
    return agent, notifications


def messages(notifications) -> list[str]:
    return [message for _, message, _ in notifications]


# --------------------------------------------------------------------- sucesso


def test_successful_dictation_types_text_and_records_insertion(make_wav, tmp_path):
    api, platform = FakeApi(text="Ola, acao!"), FakePlatform()
    agent, _ = build(api=api, platform=platform)
    recorder = FakeRecorder(make_wav(tmp_path / "a.wav"))
    agent._finish_and_transcribe(recorder, 7)

    assert platform.typed == ["Ola, acao!"]
    assert platform.targets == [7]
    assert agent.last_transcript == "Ola, acao!"
    transcription_id, inserted, insert_ms = api.inserts[0]
    assert (transcription_id, inserted) == (42, True)
    assert insert_ms is not None and insert_ms >= 0
    assert agent.busy is False
    assert not recorder.path.exists()


def test_tui_delivery_guards_before_typing(make_wav, tmp_path):
    api, platform = FakeApi(text="a\nb\t\x1b[31m", delivery="tui"), FakePlatform()
    agent, _ = build(api=api, platform=platform)
    agent._finish_and_transcribe(FakeRecorder(make_wav(tmp_path / "a.wav")), 7)

    assert platform.typed == ["a b"]
    assert agent.last_transcript == "a b"


def test_text_delivery_keeps_newlines(make_wav, tmp_path):
    api, platform = FakeApi(text="a\nb"), FakePlatform()
    agent, _ = build(api=api, platform=platform)
    agent._finish_and_transcribe(FakeRecorder(make_wav(tmp_path / "a.wav")), 7)

    assert platform.typed == ["a\nb"]


def test_uploads_the_capture_as_wav(make_wav, tmp_path):
    api = FakeApi()
    agent, _ = build(api=api)
    recorder = FakeRecorder(make_wav(tmp_path / "captura.wav"))
    agent._finish_and_transcribe(recorder, 7)

    upload = api.uploads[0]
    assert upload["content_type"] == "audio/wav"
    assert upload["filename"] == "captura.wav"
    assert upload["bytes"] > 44


def test_options_come_from_the_interface(make_wav, tmp_path):
    api = FakeApi(model="gpt-transcribe", language="en")
    agent, _ = build(api=api)
    agent._finish_and_transcribe(FakeRecorder(make_wav(tmp_path / "a.wav")), 7)
    # Sem override local, o modelo é o escolhido no servidor (web ou bandeja).
    assert api.uploads[0]["model"] == "gpt-transcribe"
    assert api.uploads[0]["language"] == "en"


def test_a_local_model_override_wins_the_server(make_wav, tmp_path):
    api = FakeApi(model="gpt-transcribe")
    agent, _ = build(api=api, preferences=Preferences(stt_model="gpt-4o-mini-transcribe"))
    agent._finish_and_transcribe(FakeRecorder(make_wav(tmp_path / "a.wav")), 7)
    assert api.uploads[0]["model"] == "gpt-4o-mini-transcribe"


def test_empty_model_preference_follows_the_server(make_wav, tmp_path):
    api = FakeApi(model="gpt-transcribe")
    agent, _ = build(api=api, preferences=Preferences(stt_model=""))
    agent._finish_and_transcribe(FakeRecorder(make_wav(tmp_path / "a.wav")), 7)
    assert api.uploads[0]["model"] == "gpt-transcribe"


def test_a_rejected_model_falls_back_to_the_server(make_wav, tmp_path):
    api = FakeApi(model="gpt-transcribe")
    api.invalid_models = {"gpt-4o-mini-transcribe"}
    agent, notifications = build(
        api=api, preferences=Preferences(stt_model="gpt-4o-mini-transcribe")
    )
    agent._finish_and_transcribe(FakeRecorder(make_wav(tmp_path / "a.wav")), 7)

    assert [item["model"] for item in api.uploads] == [None]
    assert agent._model_rejected == "gpt-4o-mini-transcribe"
    assert agent.last_transcript == "Ola, acao!"  # o ditado não se perde
    assert not any(urgency == "critical" for _, _, urgency in notifications)


def test_the_rejected_model_is_not_tried_again(make_wav, tmp_path):
    api = FakeApi(model="gpt-transcribe")
    api.invalid_models = {"gpt-4o-mini-transcribe"}
    agent, _ = build(api=api, preferences=Preferences(stt_model="gpt-4o-mini-transcribe"))
    agent._finish_and_transcribe(FakeRecorder(make_wav(tmp_path / "a.wav")), 7)
    agent.busy = False
    agent._finish_and_transcribe(FakeRecorder(make_wav(tmp_path / "b.wav")), 7)

    assert [item["model"] for item in api.uploads] == [None, None]


def test_duration_measured_from_the_wav_goes_with_the_job(make_wav, tmp_path):
    api = FakeApi()
    agent, _ = build(api=api)
    agent._finish_and_transcribe(FakeRecorder(make_wav(tmp_path / "a.wav", 0.5)), 7)

    assert api.uploads[0]["duration_s"] is not None
    assert 0.4 <= api.uploads[0]["duration_s"] <= 0.6


def test_remote_api_uploads_opus(make_wav, tmp_path, monkeypatch):
    api = FakeApi()
    api.base_url = "https://vbtyper.example.com"
    converted = tmp_path / "enviado.ogg"
    sent: list[Path] = []

    def fake_to_opus(path):
        converted.write_bytes(b"OggS" + b"\0" * 64)
        sent.append(path)
        return converted

    monkeypatch.setattr(daemon_module.compress, "to_opus", fake_to_opus)
    agent, _ = build(api=api)
    agent._finish_and_transcribe(FakeRecorder(make_wav(tmp_path / "a.wav")), 7)

    assert sent and api.uploads[0]["content_type"] == "audio/ogg"
    assert api.uploads[0]["filename"] == "enviado.ogg"
    assert not converted.exists()


def test_compression_can_be_turned_off(make_wav, tmp_path, monkeypatch):
    api = FakeApi()
    api.base_url = "https://vbtyper.example.com"
    calls: list[Path] = []
    monkeypatch.setattr(daemon_module.compress, "to_opus", lambda path: calls.append(path))
    agent, _ = build(api=api, preferences=Preferences(upload_format="wav"))
    agent._finish_and_transcribe(FakeRecorder(make_wav(tmp_path / "a.wav")), 7)

    assert calls == []
    assert api.uploads[0]["content_type"] == "audio/wav"


def test_a_failed_conversion_keeps_the_wav(make_wav, tmp_path, monkeypatch):
    api = FakeApi()
    api.base_url = "https://vbtyper.example.com"
    monkeypatch.setattr(daemon_module.compress, "to_opus", lambda path: None)
    agent, _ = build(api=api)
    agent._finish_and_transcribe(FakeRecorder(make_wav(tmp_path / "a.wav")), 7)

    assert api.uploads[0]["content_type"] == "audio/wav"
    assert api.inserts and agent.busy is False


def test_typing_preferences_reach_the_platform():
    platform = FakePlatform()
    agent, _ = build(platform=platform, preferences=Preferences(typing_batch=8, typing_delay_ms=3))
    assert platform.typing == (8, 0.003)
    assert agent.preferences.typing_batch == 8


def test_preferences_are_reloaded_while_the_client_runs():
    platform = FakePlatform()
    agent, _ = build(platform=platform)
    preferences.save(preferences.Preferences(typing_batch=4, typing_delay_ms=1))

    assert agent.reload_preferences() is True
    assert platform.typing == (4, 0.001)
    assert agent.reload_preferences() is False  # nada mudou: não rearma nada


# ------------------------------------------------------------------ falha de foco


def test_focus_loss_does_not_type_nor_mark_inserted(make_wav, tmp_path):
    api = FakeApi()
    platform = FakePlatform(type_failure=RuntimeError("O foco mudou; texto preservado."))
    agent, notifications = build(api=api, platform=platform)
    agent._finish_and_transcribe(FakeRecorder(make_wav(tmp_path / "a.wav")), 7)

    assert platform.typed == []
    assert api.inserts == []
    assert agent.last_transcript == "Ola, acao!"  # o texto não se perde
    assert any("O foco mudou" in message for message in messages(notifications))
    assert any(urgency == "critical" for _, _, urgency in notifications)


# ---------------------------------------------------------------- cancelamento


def test_cancel_during_transcription_blocks_late_insertion(make_wav, tmp_path):
    api, platform = FakeApi(), FakePlatform()
    agent, _ = build(api=api, platform=platform)
    recorder = FakeRecorder(make_wav(tmp_path / "a.wav"))
    api.on_poll = lambda: agent.cancel.set()

    agent._finish_and_transcribe(recorder, 7)

    assert platform.typed == []
    assert api.inserts == []
    assert api.cancelled == ["job-1"]
    assert not recorder.path.exists()
    assert agent.busy is False


def test_pause_cancels_and_discards_the_capture(tmp_path):
    agent, notifications = build(preferences=Preferences(notices="balloons"))
    recorder = FakeRecorder(tmp_path / "a.wav")
    agent.recorder = recorder

    agent.stop_listener()
    assert agent.worker is not None
    agent.worker.join(timeout=3)

    assert agent.cancel.is_set()
    assert recorder.discarded is True
    assert not recorder.path.exists()
    assert agent.busy is False
    assert any("Ditado pausado" in message for message in messages(notifications))


# ----------------------------------------------------------------- erros do provedor


def test_empty_result_is_nothing_new_not_an_error(make_wav, tmp_path):
    """O perfil contínuo devolve vazio quando o ditado só repetia o já escrito."""
    api, platform = FakeApi(text="   "), FakePlatform()
    agent, notifications = build(api=api, platform=platform)
    agent._finish_and_transcribe(FakeRecorder(make_wav(tmp_path / "a.wav")), 7)

    assert platform.typed == []
    assert api.inserts == []
    assert agent.last_transcript == ""
    # O indicador mostra "nada novo": é aviso de rotina, não erro.
    snapshot = agent.state_snapshot()
    assert snapshot["phase"] == "nothing"
    assert snapshot["message"] == "nada a acrescentar"


def test_failed_job_with_empty_text_still_reports_the_error(make_wav, tmp_path):
    api, platform = FakeApi(text="", status="failed", error="Falha no provedor."), FakePlatform()
    agent, notifications = build(api=api, platform=platform)
    agent._finish_and_transcribe(FakeRecorder(make_wav(tmp_path / "a.wav")), 7)

    assert platform.typed == []
    assert any("Falha no provedor" in message for message in messages(notifications))


def test_failed_job_reports_the_provider_error(make_wav, tmp_path):
    api = FakeApi(status="failed", error="Erro HTTP 500 do provedor.")
    agent, notifications = build(api=api)
    agent._finish_and_transcribe(FakeRecorder(make_wav(tmp_path / "a.wav")), 7)

    assert any("Erro HTTP 500 do provedor." in message for message in messages(notifications))


def test_broken_recorder_reports_its_stderr(make_wav, tmp_path):
    api = FakeApi()
    agent, notifications = build(api=api)
    recorder = FakeRecorder(
        make_wav(tmp_path / "a.wav"), returncode=1, interrupted=False, stderr="device busy"
    )
    agent._finish_and_transcribe(recorder, 7)

    assert api.uploads == []
    assert any("device busy" in message for message in messages(notifications))


def test_short_audio_is_refused_before_upload(tmp_path):
    api = FakeApi()
    agent, notifications = build(api=api)
    path = tmp_path / "curto.wav"
    path.write_bytes(b"RIFF" + (36).to_bytes(4, "little") + b"WAVE")
    agent._finish_and_transcribe(FakeRecorder(path), 7)

    assert api.uploads == []
    assert any(urgency == "critical" for _, _, urgency in notifications)


# ------------------------------------------------------------------- gravação


def test_recording_needs_a_target_window():
    platform = FakePlatform(window=None)
    agent, notifications = build(platform=platform)
    agent.start_recording()
    assert agent.recorder is None
    assert any(urgency == "critical" for _, _, urgency in notifications)


def test_recording_starts_once_and_reports_the_state(monkeypatch, tmp_path):
    calls: list[str] = []

    class StubRecorder:
        def __init__(self) -> None:
            self.path = tmp_path / "stub.wav"
            self.elapsed = 0.5
            self.returncode = 0
            self.level = 0

        def start(self) -> None:
            calls.append("start")

        def discard(self) -> None:
            calls.append("discard")

    monkeypatch.setattr(daemon_module, "Recorder", StubRecorder)
    agent, _ = build()
    agent.start_recording()
    agent.start_recording()

    assert calls == ["start"]
    assert agent.state_snapshot()["recording"] is True
    agent._cancel_timer()


def test_busy_agent_does_not_start_a_new_capture():
    agent, _ = build()
    agent.busy = True
    agent.start_recording()
    assert agent.recorder is None


# --------------------------------------------------------------------- atalho


def test_hotkey_drives_the_whole_dictation(monkeypatch, tmp_path, make_wav):
    """Ctrl+Super inicia a captura; soltar entrega o áudio e o texto é inserido."""
    api, platform = FakeApi(text="Texto ditado."), FakePlatform()

    class StubRecorder:
        """Substitui o arecord por um WAV já pronto."""

        def __init__(self) -> None:
            self.path = make_wav(tmp_path / "captura.wav")
            self.elapsed = 1.0
            self.returncode = 0
            self.level = 0

        def start(self) -> None:
            return None

        def stop(self) -> bool:
            return False

        def last_stderr(self) -> str:
            return ""

        def discard(self) -> None:
            self.path.unlink(missing_ok=True)

    monkeypatch.setattr(daemon_module, "Recorder", StubRecorder)
    agent, _ = build(api=api, platform=platform)
    agent.start_listener()

    platform.watcher.press("ctrl")
    platform.watcher.press("super")
    assert agent.recorder is not None
    assert agent.state_snapshot()["state"] == "recording"

    platform.watcher.release("super")
    agent.worker.join(timeout=5)

    assert api.uploads[0]["content_type"] == "audio/wav"
    assert platform.typed == ["Texto ditado."]
    assert api.inserts[0][:2] == (42, True)
    assert agent.state_snapshot()["state"] == "idle"


def test_toggle_starts_and_pauses_the_dictation():
    platform = FakePlatform()
    agent, _ = build(platform=platform)

    agent.start_listener()
    assert agent.listening is True
    assert agent.state_snapshot()["dictating"] is True

    agent.toggle_listener()
    assert agent.listening is False
    assert platform.watcher.running is False


def test_third_key_press_after_pause_is_ignored():
    platform = FakePlatform()
    agent, _ = build(platform=platform)
    agent.start_listener()
    agent.stop_listener()

    agent.state.feed("ctrl", True)
    agent.state.feed("super", True)
    agent.start_recording()
    assert agent.recorder is None  # pausado: nada é gravado


def test_listener_refuses_to_restart_while_busy():
    agent, _ = build()
    agent.busy = True
    with pytest.raises(RuntimeError, match="Aguarde"):
        agent.start_listener()


def test_listener_needs_an_x11_session(monkeypatch):
    from vb_typer_desktop.platform.linux_x11 import LinuxX11Platform

    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    agent = Daemon(
        api=FakeApi(),
        platform=LinuxX11Platform(),
        notify_fn=lambda *args: None,
        open_ui_fn=None,
    )
    with pytest.raises(RuntimeError, match="X11"):
        agent.start_listener()


# ------------------------------------------------------------------- estado


def test_state_snapshot_covers_idle_processing_and_recording(tmp_path):
    agent, _ = build()
    assert agent.state_snapshot()["state"] == "idle"
    agent.busy = True
    assert agent.state_snapshot()["state"] == "processing"
    agent.busy = False
    agent.recorder = FakeRecorder(tmp_path / "a.wav")
    assert agent.state_snapshot()["state"] == "recording"


def test_control_command_state_and_unknown():
    agent, _ = build()
    snapshot = agent.control_command("state")
    assert snapshot["ok"] is True and snapshot["dictating"] is False
    assert agent.control_command("inexistente") == {"ok": False}


def test_control_command_show_opens_the_interface():
    opened = threading.Event()
    agent = Daemon(
        api=FakeApi(),
        platform=FakePlatform(),
        notify_fn=lambda *args: None,
        open_ui_fn=lambda: opened.set() or True,
    )
    assert agent.control_command("show") == {"ok": True}
    assert opened.wait(3) is True


def test_shutdown_releases_the_waiting_caller():
    agent, _ = build()
    agent.shutdown()
    assert agent.done.is_set()
    assert agent.paused is True


# --------------------------------------------------------- indicador e avisos


def test_snapshot_offers_the_indicator_box_while_recording(tmp_path):
    agent, _ = build()
    agent.recorder = FakeRecorder(tmp_path / "a.wav")
    agent.target_window = 7
    snapshot = agent.state_snapshot()

    assert snapshot["phase"] == "recording"
    box = snapshot["indicator"]
    assert box["w"] > box["h"]
    # A caixa fica dentro da janela em foco (100,200,900,600).
    assert 100 <= box["x"] <= 900
    assert box["y"] + box["h"] <= 800


def test_snapshot_hides_the_indicator_when_idle():
    agent, _ = build()
    snapshot = agent.state_snapshot()
    assert snapshot["phase"] == "idle"
    assert "indicator" not in snapshot
    assert snapshot["level"] == 0


def test_snapshot_reports_the_microphone_level(tmp_path):
    agent, _ = build()
    recorder = FakeRecorder(tmp_path / "a.wav")
    recorder.level = 42
    agent.recorder = recorder
    assert agent.state_snapshot()["level"] == 42


def test_indicator_is_hidden_without_a_focused_window(tmp_path):
    platform = FakePlatform(window_area=None)
    agent, _ = build(platform=platform)
    agent.recorder = FakeRecorder(tmp_path / "a.wav")
    assert "indicator" not in agent.state_snapshot()


def test_indicator_is_off_in_balloons_mode(tmp_path):
    agent, _ = build(preferences=Preferences(notices="balloons"))
    agent.recorder = FakeRecorder(tmp_path / "a.wav")
    assert "indicator" not in agent.state_snapshot()


def test_indicator_follows_the_pointer_when_asked(tmp_path):
    agent, _ = build(
        preferences=Preferences(notices="indicator", anchor="pointer", position="bottom-center")
    )
    agent.recorder = FakeRecorder(tmp_path / "a.wav")
    box = agent.state_snapshot()["indicator"]
    assert box["y"] > 500  # logo abaixo do ponteiro (500, 500)


def test_routine_notices_do_not_pop_a_balloon():
    agent, notifications = build()
    agent._notify("VB Typer", "Gravando. Solte Ctrl ou Super.", "normal")
    assert notifications == []


def test_errors_reach_the_balloon_and_flash_the_indicator():
    agent, notifications = build()
    agent._notify("VB Typer — erro", "falhou", "critical")

    assert [item[2] for item in notifications] == ["critical"]
    snapshot = agent.state_snapshot()
    assert snapshot["phase"] == "error"
    assert snapshot["message"] == "falhou"


def test_balloons_mode_restores_routine_balloons():
    agent, notifications = build(preferences=Preferences(notices="balloons"))
    agent._notify("VB Typer", "Gravando.", "normal")
    assert notifications


def test_none_mode_silences_even_errors():
    agent, notifications = build(preferences=Preferences(notices="none"))
    agent._notify("VB Typer — erro", "falhou", "critical")
    assert notifications == []
    assert agent.state_snapshot()["phase"] == "error"


def test_successful_insertion_flashes_the_check(make_wav, tmp_path):
    api, platform = FakeApi(), FakePlatform()
    agent, _ = build(api=api, platform=platform)
    agent._finish_and_transcribe(FakeRecorder(make_wav(tmp_path / "a.wav")), 7)
    assert agent.state_snapshot()["phase"] == "inserted"


def test_focus_loss_flashes_the_error(make_wav, tmp_path):
    platform = FakePlatform(type_failure=RuntimeError("O foco mudou"))
    agent, _ = build(platform=platform)
    agent._finish_and_transcribe(FakeRecorder(make_wav(tmp_path / "a.wav")), 7)
    snapshot = agent.state_snapshot()
    assert snapshot["phase"] == "error"
    assert "foco mudou" in snapshot["message"]


# --------------------------------------------------------------------- modo


def test_snapshot_reports_the_current_mode():
    agent, _ = build()
    assert agent.state_snapshot()["mode"] == "literal"

    agent.mode_current = "smart"
    assert agent.state_snapshot()["mode"] == "smart"


def test_tray_can_switch_the_mode_and_it_goes_to_the_backend():
    """A troca pela bandeja grava no backend: é lá que a escolha mora."""
    api = FakeApi()
    api.patched = []
    api.patch_settings = lambda changes: api.patched.append(changes) or {"mode": changes["mode"]}
    agent, _ = build(api=api)

    assert agent.control_command("mode", "smart") == {"ok": True}
    assert api.patched == [{"mode": "smart"}]
    assert agent.current_mode == "smart"
    assert agent.state_snapshot()["mode"] == "smart"


def test_unknown_mode_is_refused_without_calling_the_backend():
    api = FakeApi()
    api.patched = []
    api.patch_settings = lambda changes: api.patched.append(changes) or {"mode": "x"}
    agent, _ = build(api=api)

    assert agent.control_command("mode", "esperto") == {"ok": False}
    assert api.patched == []


def test_a_backend_failure_keeps_the_previous_mode():
    from vb_typer_desktop.api import ApiError

    def explode(changes):
        raise ApiError("API fora do ar")

    api = FakeApi()
    api.patch_settings = explode
    agent, notifications = build(api=api)

    assert agent.control_command("mode", "smart") == {"ok": False}
    assert agent.current_mode == "literal"
    assert any(urgency == "critical" for _, _, urgency in notifications)


# -------------------------------------------------------------------- perfis


def test_refresh_options_reads_the_profiles_and_the_default():
    api = FakeApi(default_profile="email")
    agent, _ = build(api=api)
    agent.refresh_options()

    assert agent.current_profile == "email"
    snapshot = agent.state_snapshot()
    assert snapshot["profile"] == "email"
    assert snapshot["profiles"] == FakeApi.DEFAULT_PROFILES


def test_job_sends_the_profile_instead_of_the_mode(make_wav, tmp_path):
    api = FakeApi(default_profile="email")
    agent, _ = build(api=api)
    agent._finish_and_transcribe(FakeRecorder(make_wav(tmp_path / "a.wav")), 7)

    assert api.uploads[0]["profile"] == "email"
    assert api.uploads[0]["mode"] is None


def test_tray_can_switch_the_profile_and_it_goes_to_the_backend():
    """A troca pela bandeja grava no backend: é lá que a escolha mora."""
    api = FakeApi()
    agent, _ = build(api=api)
    agent.refresh_options()

    assert agent.control_command("profile", "email") == {"ok": True}
    assert api.patched == [{"default_profile": "email"}]
    assert agent.current_profile == "email"
    assert agent.state_snapshot()["profile"] == "email"


def test_unknown_profile_is_refused_without_calling_the_backend():
    api = FakeApi()
    agent, _ = build(api=api)
    agent.refresh_options()

    assert agent.control_command("profile", "inexistente") == {"ok": False}
    assert api.patched == []


def test_a_backend_failure_keeps_the_previous_profile():
    from vb_typer_desktop.api import ApiError

    def explode(changes):
        raise ApiError("API fora do ar")

    api = FakeApi(default_profile="literal")
    api.patch_settings = explode
    agent, notifications = build(api=api)
    agent.refresh_options()

    assert agent.control_command("profile", "email") == {"ok": False}
    assert agent.current_profile == "literal"
    assert any(urgency == "critical" for _, _, urgency in notifications)


def test_a_profile_deleted_in_the_interface_falls_back_to_literal():
    api = FakeApi(default_profile="email")
    agent, _ = build(api=api)
    agent.refresh_options()
    api.profiles = [{"slug": "literal", "name": "Transcrição fiel"}]

    agent.refresh_options()

    assert agent.current_profile == "literal"
    assert [item["slug"] for item in agent.profiles] == ["literal"]


def test_a_failed_refresh_never_empties_the_tray_menu():
    api = FakeApi(default_profile="email")
    agent, _ = build(api=api)
    agent.refresh_options()
    api.list_profiles = lambda: []
    api.settings_or_empty = lambda: {}

    agent.refresh_options()

    assert agent.current_profile == "email"
    assert agent.profiles == FakeApi.DEFAULT_PROFILES


def test_a_deleted_profile_clears_the_temporary_override():
    api = FakeApi()
    agent, _ = build(api=api)
    agent.refresh_options()
    agent.profile_override = "email"
    api.profiles = [{"slug": "literal", "name": "Transcrição fiel"}]

    agent.refresh_options()

    assert agent.profile_override == ""


# ------------------------------------------------- espelho com a web e a bandeja


def test_settings_are_not_reapplied_when_the_version_did_not_change():
    api = FakeApi()
    agent, _ = build(api=api)
    assert agent.refresh_options() is True
    reads = api.profile_reads

    assert agent.refresh_options() is False
    assert api.profile_reads == reads  # não busca a lista de perfis de novo


def test_a_change_made_in_the_web_reaches_the_tray():
    api = FakeApi(model="gpt-4o-mini-transcribe", language="pt", smart_model="gpt-4o-mini")
    agent, _ = build(api=api)
    agent.refresh_options()

    # A interface web (outro aparelho) trocou o modelo, o da revisão e o idioma.
    api.model = "gpt-transcribe"
    api.smart_model = "gpt-4.1-mini"
    api.language = "en"

    assert agent.refresh_options() is True
    snapshot = agent.state_snapshot()
    assert snapshot["model"] == "gpt-transcribe"
    assert snapshot["smart_model"] == "gpt-4.1-mini"
    assert snapshot["language"] == "en"


def test_the_tray_changes_the_model_and_the_next_dictation_uses_it(make_wav, tmp_path):
    api = FakeApi(model="gpt-transcribe")
    agent, _ = build(api=api)
    agent.refresh_options()

    assert agent.set_model("gpt-4o-mini-transcribe") is True
    assert api.patched == [{"model": "gpt-4o-mini-transcribe"}]
    assert agent.model == "gpt-4o-mini-transcribe"  # cache acompanha na hora
    assert agent.refresh_options() is False  # nada a reaplicar no laço seguinte

    agent._finish_and_transcribe(FakeRecorder(make_wav(tmp_path / "a.wav")), 7)
    assert api.uploads[0]["model"] == "gpt-4o-mini-transcribe"


def test_the_tray_refuses_a_model_outside_the_server_list():
    api = FakeApi()
    agent, _ = build(api=api)
    agent.refresh_options()

    assert agent.set_model("modelo-inexistente") is False
    assert api.patched == []
    assert agent.model == "gpt-4o-mini-transcribe"


def test_the_tray_changes_the_review_model():
    api = FakeApi()
    agent, _ = build(api=api)
    agent.refresh_options()

    assert agent.set_smart_model("gpt-4.1-mini") is True
    assert api.smart_model == "gpt-4.1-mini"
    assert agent.state_snapshot()["smart_model"] == "gpt-4.1-mini"
    assert agent.set_smart_model("nada-a-ver") is False


def test_the_tray_changes_the_language():
    api = FakeApi()
    agent, _ = build(api=api)
    agent.refresh_options()

    assert agent.set_language("EN") is True
    assert agent.language == "en"
    assert agent.set_language("x") is False
    assert agent.set_language("") is False


def test_control_commands_reach_the_settings():
    api = FakeApi()
    agent, _ = build(api=api)
    agent.refresh_options()

    assert agent.control_command("model", "gpt-transcribe") == {"ok": True}
    assert agent.control_command("smart_model", "gpt-4.1-mini") == {"ok": True}
    assert agent.control_command("language", "es") == {"ok": True}
    assert (api.model, api.smart_model, api.language) == ("gpt-transcribe", "gpt-4.1-mini", "es")


def test_the_snapshot_carries_the_choices_for_the_tray():
    api = FakeApi(model="gpt-transcribe", smart_model="gpt-4.1-mini")
    agent, _ = build(api=api)
    agent.refresh_options()

    snapshot = agent.state_snapshot()
    assert snapshot["model"] == "gpt-transcribe"
    assert snapshot["smart_model"] == "gpt-4.1-mini"
    assert snapshot["models"] == ["gpt-4o-mini-transcribe", "gpt-transcribe"]
    assert snapshot["smart_models"] == ["gpt-4o-mini", "gpt-4.1-mini"]


# --------------------------------------------------------- atalhos de perfil


def test_shortcut_cycles_the_profile_without_changing_the_default():
    api, platform = FakeApi(default_profile="literal"), FakePlatform()
    agent, _ = build(api=api, platform=platform)
    agent.start_listener()
    agent.refresh_options()

    platform.combos.fire("profile_next")

    assert agent.current_profile == "revisado"
    # A troca por atalho é temporária: nada foi gravado no backend.
    assert api.patched == []
    snapshot = agent.state_snapshot()
    assert snapshot["profile"] == "revisado"
    assert snapshot["phase"] == "profile"
    assert snapshot["message"] == "Texto revisado"
    assert snapshot["message_detail"] == "2/3"
    assert snapshot["indicator"]["w"] == 200
    agent.stop_listener()


def test_shortcut_counts_the_position_and_wraps(make_wav, tmp_path):
    api, platform = FakeApi(default_profile="literal"), FakePlatform()
    agent, _ = build(api=api, platform=platform)
    agent.start_listener()
    agent.refresh_options()

    platform.combos.fire("profile_previous")  # literal -> email (dá a volta)

    assert agent.current_profile == "email"
    # O próximo ditado vai com o perfil do ciclo.
    agent._finish_and_transcribe(FakeRecorder(make_wav(tmp_path / "a.wav")), 7)
    assert api.uploads[0]["profile"] == "email"
    agent.stop_listener()


def test_default_shortcut_goes_back_to_the_configured_default():
    api, platform = FakeApi(default_profile="email"), FakePlatform()
    agent, _ = build(api=api, platform=platform)
    agent.start_listener()
    agent.refresh_options()

    platform.combos.fire("profile_next")  # email é o último: volta ao literal
    assert agent.current_profile == "literal"

    platform.combos.fire("profile_default")

    assert agent.current_profile == "email"
    snapshot = agent.state_snapshot()
    assert snapshot["phase"] == "profile"
    assert snapshot["message"] == "E-mail profissional"
    assert snapshot["message_detail"] == "padrão"
    agent.stop_listener()


def test_shortcut_is_ignored_while_dictating_or_processing():
    api, platform = FakeApi(default_profile="literal"), FakePlatform()
    agent, _ = build(api=api, platform=platform)
    agent.start_listener()
    agent.refresh_options()
    agent.busy = True

    platform.combos.fire("profile_next")

    assert agent.current_profile == "literal"
    agent.stop_listener()


def test_tray_choice_clears_the_temporary_cycle():
    api, platform = FakeApi(default_profile="literal"), FakePlatform()
    agent, _ = build(api=api, platform=platform)
    agent.start_listener()
    agent.refresh_options()
    platform.combos.fire("profile_next")
    assert agent.current_profile == "revisado"

    assert agent.control_command("profile", "email") == {"ok": True}

    assert agent.current_profile == "email"
    assert agent.profile_override == ""
    agent.stop_listener()


def test_shortcut_registers_the_bindings_from_the_settings():
    api, platform = FakeApi(), FakePlatform()
    agent, _ = build(api=api, platform=platform)
    agent.start_listener()
    agent.refresh_options()

    assert platform.combos.running is True
    assert platform.combos.bindings["profile_next"] == (("ctrl", "alt"), "Tab")
    agent.stop_listener()
    assert platform.combos.running is False


def test_a_changed_shortcut_rearms_the_grab():
    api, platform = FakeApi(), FakePlatform()
    agent, _ = build(api=api, platform=platform)
    agent.start_listener()
    agent.refresh_options()
    first = platform.combos

    api.hotkeys = {
        "profile_next": "ctrl+alt+F9",
        "profile_previous": "ctrl+alt+F10",
        "profile_default": "ctrl+alt+0",
    }
    agent.refresh_options()

    assert first.running is False
    assert len(platform.combo_watchers) == 2
    assert platform.combos.bindings["profile_next"] == (("ctrl", "alt"), "F9")
    agent.stop_listener()


def test_a_grab_failure_warns_once_and_the_dictation_goes_on():
    api, platform = FakeApi(), FakePlatform()
    agent, notifications = build(api=api, platform=platform)
    agent.start_listener()

    platform.combos.fail("combinação em uso")
    platform.combos.fail("combinação em uso")

    assert sum("atalho indisponível" in message for message in messages(notifications)) == 1
    assert agent.listening is True
    agent.stop_listener()


def test_platform_without_combo_support_keeps_dictation_working():
    api, platform = FakeApi(), FakePlatform()
    platform.combo_watcher = None  # capacidade opcional ausente
    agent, _ = build(api=api, platform=platform)

    agent.start_listener()

    assert agent.listening is True
    assert agent.combo_watcher is None
    agent.stop_listener()


def test_nothing_new_is_success_and_types_nothing():
    """Ditado que só repetia o que já estava escrito: avisa, não insere, não é erro."""
    api, platform = FakeApi(), FakePlatform()
    agent, _ = build(api=api, platform=platform)

    agent._insert(Job(id="job-1", status="succeeded", text="", transcription_id=42), 7)

    assert platform.typed == []
    assert api.inserts == []
    snapshot = agent.state_snapshot()
    assert snapshot["phase"] == "nothing"
    assert snapshot["message"] == "nada a acrescentar"


# ------------------------------------------------------------------- onda


def test_snapshot_carries_the_waveform_while_recording():
    agent, _ = build()
    recorder = FakeRecorder(Path("captura.wav"))
    agent.recorder = recorder

    assert agent.state_snapshot()["waveform"] == recorder.waveform_data


def test_waveform_is_not_sent_while_idle():
    agent, _ = build()

    assert "waveform" not in agent.state_snapshot()


def test_waveform_is_skipped_when_the_shape_is_the_bar():
    agent, _ = build(preferences=Preferences(shape="bar"))
    agent.recorder = FakeRecorder(Path("captura.wav"))

    assert "waveform" not in agent.state_snapshot()


def test_waveform_is_skipped_without_the_visual_indicator():
    agent, _ = build(preferences=Preferences(notices="none"))
    agent.recorder = FakeRecorder(Path("captura.wav"))

    assert "waveform" not in agent.state_snapshot()


def test_recorder_without_waveform_is_tolerated():
    """Um gravador de outra plataforma pode não oferecer a onda."""
    agent, _ = build()
    agent.recorder = SimpleNamespace(level=5)

    assert "waveform" not in agent.state_snapshot()


# -------------------------------------------------------- fase do processamento


def test_snapshot_reports_the_job_phase():
    agent, _ = build()
    assert agent.state_snapshot()["job_phase"] == ""

    agent.busy = True
    agent.job_phase = "rendering"
    assert agent.state_snapshot()["job_phase"] == "rendering"


def test_wait_for_terminal_tracks_the_backend_phase():
    api = FakeApi(status="succeeded", phase="rendering")
    agent, _ = build(api=api)

    agent._wait_for_terminal(Job(id="job-1", status="running"))

    assert agent.job_phase == "rendering"


def test_the_first_poll_does_not_wait():
    api = FakeApi(status="running")
    # Intervalo enorme: se esperasse antes da primeira consulta, o teste travaria.
    agent, _ = build(api=api, poll_interval=30.0)

    def finish():
        api.status = "succeeded"

    api.on_poll = finish
    started = time.monotonic()
    job = agent._wait_for_terminal(Job(id="job-1", status="queued"))

    assert job is not None and job.status == "succeeded"
    assert api.polls == 1
    assert time.monotonic() - started < 1


def test_poll_delay_grows_up_to_the_ceiling():
    agent, _ = build(poll_interval=0.15)

    assert agent._next_poll_delay(0) == 0.15
    assert agent._next_poll_delay(0.15) == 0.3
    assert round(agent._next_poll_delay(0.3), 2) == 0.6
    assert agent._next_poll_delay(0.6) == POLL_MAX_INTERVAL_S
    assert agent._next_poll_delay(POLL_MAX_INTERVAL_S) == POLL_MAX_INTERVAL_S


def test_a_zero_interval_never_waits():
    agent, _ = build(poll_interval=0.0)
    assert agent._next_poll_delay(0) == 0.0
    assert agent._next_poll_delay(5) == 0.0


def test_settings_are_read_once_and_then_kept(make_wav, tmp_path):
    api = FakeApi()
    agent, _ = build(api=api)
    agent._finish_and_transcribe(FakeRecorder(make_wav(tmp_path / "a.wav")), 7)
    first = api.settings_reads
    agent._finish_and_transcribe(FakeRecorder(make_wav(tmp_path / "b.wav")), 7)

    assert first >= 1
    assert api.settings_reads == first  # o segundo ditado não pede de novo


def test_job_phase_is_cleared_when_the_dictation_ends(make_wav, tmp_path):
    api = FakeApi(status="succeeded", phase="rendering")
    agent, _ = build(api=api)

    agent._finish_and_transcribe(FakeRecorder(make_wav(tmp_path / "a.wav")), 7)

    assert agent.job_phase == ""
