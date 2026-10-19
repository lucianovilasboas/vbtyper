"""CLI: status, autoteste e recusa de uma segunda instância."""

from __future__ import annotations

import pytest

from vb_typer_desktop import __main__ as main_module


@pytest.fixture
def fake_running(monkeypatch):
    monkeypatch.setattr(main_module, "talk_to_running_instance", lambda cmd: {"ok": True})


def test_version_short_circuits(capsys):
    assert main_module.main(["--version"]) == 0
    assert "VB Typer Desktop" in capsys.readouterr().out


def test_second_instance_defers_to_the_running_one(monkeypatch, fake_running):
    started: list[dict] = []
    notifications: list[tuple] = []
    monkeypatch.setattr(main_module, "run_daemon", lambda *a, **k: started.append(k) or 0)
    monkeypatch.setattr(main_module, "notify", lambda *a: notifications.append(a))

    assert main_module.main([]) == 0
    assert started == []
    assert notifications


def test_force_ignores_the_running_instance(monkeypatch, fake_running):
    started: list[dict] = []
    monkeypatch.setattr(main_module, "run_daemon", lambda *a, **k: started.append(k) or 0)

    assert main_module.main(["--force"]) == 0
    assert started[0]["with_tray"] is True
    assert started[0]["open_browser"] is False
    assert started[0]["prefs"].shows_indicator is True


def test_starts_when_nothing_is_running(monkeypatch):
    monkeypatch.setattr(main_module, "talk_to_running_instance", lambda cmd: None)
    started: list[dict] = []
    monkeypatch.setattr(main_module, "run_daemon", lambda *a, **k: started.append(k) or 0)

    assert main_module.main(["--no-tray", "--ui"]) == 0
    assert started[0]["with_tray"] is False
    assert started[0]["open_browser"] is True


def test_notices_flag_restores_the_old_behaviour(monkeypatch):
    monkeypatch.setattr(main_module, "talk_to_running_instance", lambda cmd: None)
    started: list[dict] = []
    monkeypatch.setattr(main_module, "run_daemon", lambda *a, **k: started.append(k) or 0)

    assert main_module.main(["--notices", "balloons"]) == 0
    prefs = started[0]["prefs"]
    assert prefs.shows_routine_balloons is True
    assert prefs.shows_indicator is False


def test_self_test_reports_a_missing_recorder(monkeypatch, capsys):
    from vb_typer_desktop import __main__ as module

    monkeypatch.setattr(module.shutil, "which", lambda _: None)

    class Api:
        base_url = "http://127.0.0.1:8765"

        def ready(self):
            return {"status": "ok", "database": True, "api_key_configured": True}

        def close(self):
            return None

    assert module._self_test(Api()) == 1
    assert "arecord" in capsys.readouterr().err


def test_stop_signal_shuts_down_by_the_normal_path():
    """SIGTERM precisa encerrar pelo fluxo normal, senão o systemd mata o
    processo e deixa bandeja e indicador órfãos."""
    import signal
    import threading

    class FakeDaemon:
        def __init__(self):
            self.done = threading.Event()

    daemon = FakeDaemon()
    original = signal.getsignal(signal.SIGTERM)
    try:
        main_module._install_stop_handlers(daemon)
        handler = signal.getsignal(signal.SIGTERM)
        assert callable(handler)
        assert not daemon.done.is_set()
        handler(signal.SIGTERM, None)
        assert daemon.done.is_set()
    finally:
        signal.signal(signal.SIGTERM, original)
