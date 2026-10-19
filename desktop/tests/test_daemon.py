"""Ciclo do ditado: atalho, gravação, transcrição, cancelamento e inserção."""

from __future__ import annotations

import threading

import pytest

from fakes import FakeApi, FakePlatform, FakeRecorder
from vb_typer_desktop import daemon as daemon_module
from vb_typer_desktop.daemon import Daemon


def build(api=None, platform=None, **kwargs):
    notifications: list[tuple[str, str, str]] = []

    def notify(title: str, message: str, urgency: str = "normal") -> None:
        notifications.append((title, message, urgency))

    agent = Daemon(
        api=api or FakeApi(),
        platform=platform or FakePlatform(),
        notify_fn=notify,
        poll_interval=0.0,
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
    assert api.uploads[0]["model"] == "gpt-transcribe"
    assert api.uploads[0]["language"] == "en"


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
    agent, notifications = build()
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


def test_empty_transcription_is_an_error(make_wav, tmp_path):
    api, platform = FakeApi(text="   "), FakePlatform()
    agent, notifications = build(api=api, platform=platform)
    agent._finish_and_transcribe(FakeRecorder(make_wav(tmp_path / "a.wav")), 7)

    assert platform.typed == []
    assert api.inserts == []
    assert any("não reconheceu fala" in message for message in messages(notifications))


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
