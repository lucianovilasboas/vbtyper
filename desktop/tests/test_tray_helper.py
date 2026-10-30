"""Bandeja: funções puras do helper GTK, carregadas sem abrir janela."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[1] / "tray" / "tray_helper.py"


@pytest.fixture(scope="module")
def tray():
    spec = importlib.util.spec_from_file_location("vb_typer_tray", HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_profile_label_marks_only_the_current_one(tray):
    assert tray.profile_label("E-mail profissional", True) == "E-mail profissional ✓"
    assert tray.profile_label("E-mail profissional", False) == "E-mail profissional"


def test_signature_keeps_the_order_and_ignores_invalid_entries(tray):
    signature = tray.profile_signature(
        [
            {"slug": "literal", "name": "Transcrição fiel"},
            {"name": "sem slug"},
            {"slug": "email", "name": "E-mail profissional"},
            "texto solto",
        ]
    )
    assert signature == (
        ("literal", "Transcrição fiel"),
        ("email", "E-mail profissional"),
    )


def test_signature_falls_back_to_the_slug_as_name(tray):
    assert tray.profile_signature([{"slug": "ata"}]) == (("ata", "ata"),)


def test_signature_changes_when_a_profile_is_added_or_renamed(tray):
    one = tray.profile_signature([{"slug": "literal", "name": "Transcrição fiel"}])
    renamed = tray.profile_signature([{"slug": "literal", "name": "Fiel"}])
    added = tray.profile_signature(
        [{"slug": "literal", "name": "Transcrição fiel"}, {"slug": "ata", "name": "Ata"}]
    )
    assert one != renamed
    assert one != added


def test_signature_accepts_an_empty_snapshot(tray):
    assert tray.profile_signature([]) == ()
    assert tray.profile_signature(None) == ()


def test_icon_colours_still_follow_the_state(tray):
    assert tray.icon_name(True, False) == "tray_on"
    assert tray.icon_name(False, False) == "tray_off"
    assert tray.icon_name(True, True, blink=False) == "tray_on"
    assert tray.icon_name(True, True, blink=True) == "tray_rec"
    assert tray.icon_name(True, False, processing=True) == "tray_busy"
    assert tray.icon_name(True, False, processing=True, busy_alt=True) == "tray_busy_alt"


def test_helper_imports_gtk_only_inside_the_tray(tray):
    """Roda no Python do sistema: o import de ``gi`` não pode estar no topo."""
    source = HELPER.read_text(encoding="utf-8")
    header = source.split('"""', 2)[2]
    assert "import gi" not in header.split("class Tray")[0]


def test_helper_rejects_missing_arguments(tray, monkeypatch):
    monkeypatch.setattr("sys.argv", ["tray_helper.py"])
    assert tray.main() == 2


# ------------------------------------------- escolhas do servidor na bandeja


class FakeItem:
    def __init__(self, label=""):
        self.label = label
        self.shown = True
        self.handlers = []
        self.submenu = None

    def connect(self, event, handler):
        self.handlers.append(handler)

    def set_submenu(self, menu):
        self.submenu = menu

    def set_label(self, label):
        self.label = label

    def show(self):
        self.shown = True

    def hide(self):
        self.shown = False

    def activate(self):
        for handler in self.handlers:
            handler(self)


class FakeMenu:
    def __init__(self):
        self.children = []

    def append(self, item):
        self.children.append(item)

    def remove(self, item):
        self.children.remove(item)


class FakeGtk:
    MenuItem = FakeItem
    Menu = FakeMenu


def test_choice_signature_ignores_empty_items(tray):
    assert tray.choice_signature(["a", "", None, "b"]) == ("a", "b")
    assert tray.choice_signature([]) == ()
    assert tray.choice_signature(None) == ()


def test_language_label_shows_the_name_and_the_code(tray):
    assert tray.language_label("pt") == "Português (pt)"
    assert tray.language_label("xx") == "xx"


def test_choice_menu_marks_the_current_one_and_sends_the_click(tray):
    sent = []
    root = FakeMenu()
    menu = tray.ChoiceMenu(
        FakeGtk, root, "Modelo", "model", lambda command, value: sent.append((command, value))
    )

    menu.sync(["a", "b"], "b")

    assert menu.item.label == "Modelo"
    assert root.children == [menu.item]
    assert [item.label for item in menu.submenu.children] == ["a", "b ✓"]

    menu.submenu.children[0].activate()
    assert sent == [("model", "a")]

    menu.sync(["a", "b"], "a")
    assert [item.label for item in menu.submenu.children] == ["a ✓", "b"]


def test_choice_menu_rebuilds_only_when_the_list_changes(tray):
    menu = tray.ChoiceMenu(FakeGtk, FakeMenu(), "Idioma", "language", lambda *_: None)
    menu.sync(["pt", "en"], "pt")
    built = list(menu.submenu.children)

    menu.sync(["pt", "en"], "en")
    assert menu.submenu.children == built  # mesma lista: só remarca

    menu.sync(["pt", "en", "es"], "en")
    assert len(menu.submenu.children) == 3
    assert menu.submenu.children[0] is not built[0]


def test_choice_menu_hides_when_the_server_has_no_choices(tray):
    menu = tray.ChoiceMenu(FakeGtk, FakeMenu(), "Modelo", "model", lambda *_: None)

    menu.sync([], "")
    assert menu.item.shown is False

    menu.sync(["a"], "a")
    assert menu.item.shown is True
