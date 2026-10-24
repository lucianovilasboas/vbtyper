"""Ciclo de perfis e leitura das combinações — sem X, sem rede."""

from __future__ import annotations

from vb_typer_desktop.profile_switch import (
    DEFAULT_HOTKEYS,
    PROFILE_DEFAULT,
    PROFILE_NEXT,
    PROFILE_PREVIOUS,
    bindings,
    next_profile,
    parse_hotkey,
)

PROFILES = ["literal", "revisado", "email"]


def test_next_profile_walks_forward_and_wraps():
    assert next_profile(PROFILES, "literal") == "revisado"
    assert next_profile(PROFILES, "revisado") == "email"
    assert next_profile(PROFILES, "email") == "literal"


def test_previous_profile_walks_backwards_and_wraps():
    assert next_profile(PROFILES, "literal", -1) == "email"
    assert next_profile(PROFILES, "email", -1) == "revisado"


def test_profile_absent_from_the_list_restarts_at_the_edge():
    assert next_profile(PROFILES, "apagado") == "literal"
    assert next_profile(PROFILES, "apagado", -1) == "email"


def test_no_profiles_keeps_the_current_one():
    assert next_profile([], "literal") == "literal"


def test_parse_accepts_the_default_combinations():
    for text in DEFAULT_HOTKEYS.values():
        assert parse_hotkey(text) is not None


def test_parse_returns_the_modifiers_in_canonical_order():
    assert parse_hotkey("ALT+ctrl+Tab") == (("ctrl", "alt"), "Tab")


def test_parse_rejects_combination_without_modifier():
    assert parse_hotkey("Tab") is None
    assert parse_hotkey("") is None


def test_parse_rejects_ctrl_super():
    """Ctrl+Super é o atalho de gravar: ali começaria um ditado."""
    assert parse_hotkey("ctrl+super+Tab") is None


def test_parse_rejects_unknown_modifier_and_repetition():
    assert parse_hotkey("ctrl+hiper+Tab") is None
    assert parse_hotkey("ctrl+ctrl+Tab") is None


def test_bindings_skips_what_cannot_be_grabbed():
    parsed = bindings(
        {
            PROFILE_NEXT: "ctrl+alt+Tab",
            PROFILE_PREVIOUS: "ctrl+super+Tab",  # colide com o ditado
            PROFILE_DEFAULT: "ctrl+alt+0",
            "acao_desconhecida": "ctrl+alt+9",
        }
    )

    assert set(parsed) == {PROFILE_NEXT, PROFILE_DEFAULT}
    assert parsed[PROFILE_NEXT] == (("ctrl", "alt"), "Tab")
