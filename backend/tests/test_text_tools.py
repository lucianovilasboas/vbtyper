"""Ferramentas determinísticas do pipeline de texto."""

from __future__ import annotations

import pytest

from vb_typer.domain.text_tools import (
    apply_tools,
    effective_tools,
    single_line,
    strip_ansi,
    strip_control,
    strip_markdown,
    target_hint,
    validate_tools,
)


def test_single_line_covers_crlf_cr_vt_ff_nel_and_unicode_separators():
    text = "a\r\nb\rc\vd\fe\x85f\u2028g\u2029h"
    assert single_line(text) == "a b c d e f g h"


def test_single_line_collapses_spaces_and_trims():
    assert single_line("  a\t\tb   c  ") == "a b c"


def test_single_line_is_idempotent():
    once = single_line("a\nb")
    assert single_line(once) == once


def test_strip_ansi_removes_csi_and_osc():
    assert strip_ansi("\x1b[31mvermelho\x1b[0m") == "vermelho"
    assert strip_ansi("\x1b]0;título\x07texto") == "texto"


def test_strip_control_removes_c0_c1_and_del_but_keeps_whitespace():
    assert strip_control("a\x00b\x1bc\x7fd\x9fe\nf\tg") == "abcde\nf\tg"


def test_strip_markdown_is_conservative():
    source = "```py\nx = 1\n```\n# Título\n- item\n> citação\n**negrito** `código`"
    result = strip_markdown(source)
    assert "```" not in result
    assert "# Título" not in result
    assert "- item" not in result
    assert "> citação" not in result
    assert "**negrito**" not in result
    assert "negrito código" in result
    assert "x = 1" in result


def test_tools_only_run_in_allowed_phases():
    with pytest.raises(ValueError):
        validate_tools(["single_line"], "before")
    assert validate_tools(["strip_ansi", "strip_control"], "before") == [
        "strip_ansi",
        "strip_control",
    ]


def test_unknown_tool_is_rejected():
    with pytest.raises(ValueError):
        validate_tools(["nao-existe"], "after")


def test_effective_tools_extras_come_before_the_target_preset():
    assert effective_tools("tui", ["strip_markdown"]) == [
        "strip_markdown",
        "strip_ansi",
        "spaces_for_tabs",
        "single_line",
        "strip_control",
        "trim",
    ]
    assert effective_tools("text", ["strip_markdown"]) == ["strip_markdown"]
    assert effective_tools("text") == []


def test_effective_tools_validates_the_delivery():
    with pytest.raises(ValueError):
        effective_tools("telepatia")


def test_tui_preset_keeps_words_apart_and_removes_enter_and_controls():
    text = "linha 1\nlinha 2\t\x1b[31m\x00fim"
    result = apply_tools(text, effective_tools("tui"))
    assert result == "linha 1 linha 2 fim"
    assert "\n" not in result and "\r" not in result and "\t" not in result
    assert apply_tools(result, effective_tools("tui")) == result


def test_target_hints():
    assert "única linha" in target_hint("tui")
    assert target_hint("text") == ""
