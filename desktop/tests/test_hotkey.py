"""Atalho global: segurar Ctrl+Super inicia; soltar qualquer uma encerra."""

from __future__ import annotations

from vb_typer_desktop.hotkey import HotkeyState


def test_starts_only_with_both_keys_pressed():
    state = HotkeyState()
    assert state.feed("ctrl", True) is None
    assert state.feed("super", True) == "start"
    assert state.recording is True
    assert state.feed("super", True) is None


def test_starts_when_super_arrives_first():
    state = HotkeyState()
    assert state.feed("super", True) is None
    assert state.feed("ctrl", True) == "start"


def test_releasing_either_key_stops():
    state = HotkeyState()
    state.feed("ctrl", True)
    state.feed("super", True)
    assert state.feed("ctrl", False) == "stop"
    assert state.recording is False
    assert state.feed("super", False) is None


def test_ignores_unrelated_keys():
    state = HotkeyState()
    assert state.feed(None, True) is None
    assert state.feed("shift", True) is None
    assert state.recording is False


def test_release_without_press_does_not_stop():
    state = HotkeyState()
    assert state.feed("ctrl", False) is None
    assert state.recording is False


def test_restart_after_release():
    state = HotkeyState()
    state.feed("ctrl", True)
    state.feed("super", True)
    state.feed("super", False)
    state.feed("ctrl", False)
    state.feed("ctrl", True)
    assert state.feed("super", True) == "start"
