"""Guardas de entrega: TUI limpa Enter/Tab/ESC; texto normal passa intacto."""

from __future__ import annotations

from vb_typer_desktop.text_guards import apply_guard, tui_guard


def test_tui_guard_removes_line_breaks_tabs_ansi_and_controls():
    text = "linha 1\nlinha 2\r\nlinha 3\t\x1b[31m\x00fim"
    result = tui_guard(text)
    assert result == "linha 1 linha 2 linha 3 fim"
    assert "\n" not in result and "\r" not in result and "\t" not in result


def test_tui_guard_is_idempotent():
    once = tui_guard("a\nb")
    assert tui_guard(once) == once


def test_text_delivery_is_untouched():
    assert apply_guard("a\nb\tc", "text") == "a\nb\tc"


def test_unknown_delivery_is_identity():
    """Um destino novo no backend não pode ser mutilado por um cliente antigo."""
    assert apply_guard("a\nb", "destino-futuro") == "a\nb"


def test_guard_registry_has_tui():
    from vb_typer_desktop.text_guards import GUARDS

    assert GUARDS["tui"] is tui_guard
