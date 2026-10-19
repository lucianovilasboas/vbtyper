"""A digitação é direta no cursor: nada de área de transferência nem ativação de janela."""

from __future__ import annotations

from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "src" / "vb_typer_desktop"

# Se qualquer um destes aparecer no código, a inserção deixou de ser direta no
# cursor e passou a colar/ativar janela — exatamente o que não pode acontecer.
FORBIDDEN = (
    "xclip",
    "xsel",
    "wl-copy",
    "pyperclip",
    "clipboard",
    "selection_get",
    "set_selection_owner",
    "_net_active_window",
    "set_input_focus",
    "paste",
)


def source_files() -> list[Path]:
    return sorted(SOURCE.rglob("*.py"))


def test_source_tree_is_present():
    assert source_files(), "nenhum módulo encontrado para auditar"


@pytest.mark.parametrize("token", FORBIDDEN)
def test_no_clipboard_or_focus_activation_call(token):
    for path in source_files():
        text = path.read_text(encoding="utf-8").lower()
        assert token not in text, f"{token!r} encontrado em {path}"


def test_direct_typing_is_the_insertion_api():
    from vb_typer_desktop.platform import linux_x11

    assert callable(linux_x11.type_text)
    assert not hasattr(linux_x11, "paste_text")
    assert not hasattr(linux_x11, "restore_window")
