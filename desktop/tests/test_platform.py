"""Adaptador Linux/X11: sessão gráfica, atalho por polling, foco e digitação."""

from __future__ import annotations

import os
import threading
import time

import pytest

from vb_typer_desktop.platform.linux_x11 import (
    KEY_BATCH,
    LinuxX11Platform,
    ModifierWatcher,
    modifier_groups,
    read_active_window,
    type_strokes,
    type_text,
)

CTRL_CODE = 37
SUPER_CODE = 133


def bitmap_with(*keycodes: int) -> bytes:
    data = bytearray(32)
    for keycode in keycodes:
        data[keycode // 8] |= 1 << (keycode % 8)
    return bytes(data)


def reader_of(source):
    """Fábrica de leitor para os testes: um callable sem conexão para fechar."""

    def factory():
        return source

    return factory


# ------------------------------------------------------------------- sessão


def test_wayland_is_refused(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("DISPLAY", ":0")
    with pytest.raises(RuntimeError, match="X11"):
        LinuxX11Platform().ensure_session()


def test_missing_display_is_refused(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.delenv("DISPLAY", raising=False)
    with pytest.raises(RuntimeError, match="DISPLAY"):
        LinuxX11Platform().ensure_session()


def test_x11_session_is_accepted(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.setenv("DISPLAY", ":0")
    LinuxX11Platform().ensure_session()


# ------------------------------------------------------------------- atalho


def test_watcher_reports_press_and_release_in_order():
    events: list[tuple[str, bool]] = []
    watcher = ModifierWatcher(
        groups={CTRL_CODE: "ctrl", SUPER_CODE: "super"},
        on_change=lambda group, pressed: events.append((group, pressed)),
    )
    watcher.apply(bitmap_with())
    watcher.apply(bitmap_with(CTRL_CODE))
    watcher.apply(bitmap_with(CTRL_CODE, SUPER_CODE))
    watcher.apply(bitmap_with(SUPER_CODE))
    watcher.apply(bitmap_with())
    assert events == [
        ("ctrl", True),
        ("super", True),
        ("ctrl", False),
        ("super", False),
    ]


def test_watcher_does_not_repeat_steady_state():
    events: list[tuple[str, bool]] = []
    watcher = ModifierWatcher(
        groups={CTRL_CODE: "ctrl"}, on_change=lambda *args: events.append(args)
    )
    for _ in range(5):
        watcher.apply(bitmap_with(CTRL_CODE))
    assert events == [("ctrl", True)]


def test_watcher_ignores_out_of_range_keycodes():
    watcher = ModifierWatcher(groups={900: "ctrl"}, on_change=lambda *args: None)
    watcher.apply(bitmap_with())  # não deve estourar


def test_watcher_thread_stops_deterministically():
    watcher = ModifierWatcher(
        groups={CTRL_CODE: "ctrl"},
        on_change=lambda *args: None,
        interval=0.005,
        reader_factory=reader_of(lambda: bitmap_with(CTRL_CODE)),
    )
    watcher.start()
    assert watcher.running is True
    watcher.stop()
    assert watcher.running is False


def test_watcher_thread_delivers_events():
    events: list[tuple[str, bool]] = []
    current = {"bitmap": bitmap_with()}
    watcher = ModifierWatcher(
        groups={CTRL_CODE: "ctrl"},
        on_change=lambda group, pressed: events.append((group, pressed)),
        interval=0.005,
        reader_factory=reader_of(lambda: current["bitmap"]),
    )
    watcher.start()
    try:
        time.sleep(0.05)
        current["bitmap"] = bitmap_with(CTRL_CODE)
        time.sleep(0.05)
        current["bitmap"] = bitmap_with()
        time.sleep(0.05)
    finally:
        watcher.stop()
    assert events == [("ctrl", True), ("ctrl", False)]


def test_watcher_reports_a_broken_reader(capsys):
    def exploding() -> bytes:
        raise OSError("conexão X caiu")

    watcher = ModifierWatcher(
        groups={CTRL_CODE: "ctrl"},
        on_change=lambda *args: None,
        interval=0.005,
        reader_factory=reader_of(exploding),
    )
    watcher.start()
    time.sleep(0.02)
    watcher.stop()
    assert watcher.running is False
    assert "interrompido" in capsys.readouterr().err


def test_watcher_reports_an_unavailable_connection(capsys):
    def unavailable():
        raise RuntimeError("sem DISPLAY")

    watcher = ModifierWatcher(
        groups={CTRL_CODE: "ctrl"},
        on_change=lambda *args: None,
        interval=0.005,
        reader_factory=unavailable,
    )
    watcher.start()
    time.sleep(0.02)
    watcher.stop()
    assert "indisponível" in capsys.readouterr().err


@pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="requer sessão X")
def test_modifier_groups_finds_control_keys():
    assert "ctrl" in modifier_groups().values()


# ------------------------------------------------------------ foco e digitação


def test_read_active_window_without_display_returns_none(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    assert read_active_window() is None


def test_typing_without_target_window_is_refused():
    with pytest.raises(RuntimeError, match="O foco mudou"):
        type_text("Ola", None)


def test_typing_with_cancelled_event_is_refused():
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(RuntimeError, match="cancelada"):
        type_text("Ola", 1, cancel)


# --------------------------------------------------------- lote de digitação


def strokes(count: int, shift_at: int | None = None) -> list[tuple[int, bool, int | None]]:
    return [(10 + index, index == shift_at, 50) for index in range(count)]


def run_strokes(items, **kwargs):
    """Digita com dublês no lugar do X e conta as idas ao servidor."""
    calls = {"sync": 0, "before": 0, "focus": 0, "pressed": [], "released": []}

    type_strokes(
        items,
        press=calls["pressed"].append,
        release=calls["released"].append,
        sync=lambda: calls.__setitem__("sync", calls["sync"] + 1),
        before_batch=lambda: calls.__setitem__("before", calls["before"] + 1),
        check_focus=lambda: calls.__setitem__("focus", calls["focus"] + 1),
        **kwargs,
    )
    return calls


def test_keystrokes_are_sent_in_batches():
    calls = run_strokes(strokes(40))

    assert calls["pressed"] == [10 + index for index in range(40)]
    assert calls["released"] == [10 + index for index in range(40)]
    # 40 teclas em lotes de 16: 3 sincronizações + a final do lote incompleto.
    assert calls["sync"] == 3
    assert calls["before"] == 3
    assert calls["focus"] == 1  # só a conferência final


def test_every_batch_checks_focus_and_modifiers():
    calls = run_strokes(strokes(20), batch=5)

    assert calls["before"] == 4
    assert calls["sync"] == 4


def test_shift_wraps_the_letter_it_belongs_to():
    calls = run_strokes([(10, False, 50), (11, True, 50)], batch=16)

    assert calls["pressed"] == [10, 50, 11]
    assert calls["released"] == [10, 11, 50]


def test_cancellation_stops_between_keystrokes():
    cancel = threading.Event()
    pressed = []

    def press(code):
        pressed.append(code)
        if len(pressed) >= 2:
            cancel.set()

    with pytest.raises(RuntimeError, match="cancelada"):
        type_strokes(
            strokes(10),
            press=press,
            release=lambda code: None,
            sync=lambda: None,
            before_batch=lambda: None,
            check_focus=lambda: None,
            cancel=cancel,
        )
    assert len(pressed) == 2


def test_platform_typing_rhythm_can_be_configured():
    platform = LinuxX11Platform()
    assert platform.batch == KEY_BATCH and platform.key_delay == 0.0

    platform.configure_typing(4, 0.002)
    assert (platform.batch, platform.key_delay) == (4, 0.002)

    platform.configure_typing(0, -1)
    assert (platform.batch, platform.key_delay) == (1, 0.0)
