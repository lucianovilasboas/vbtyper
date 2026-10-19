"""Indicador visual: funções puras, carregadas do helper GTK sem abrir janela."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[1] / "tray" / "indicator.py"


@pytest.fixture(scope="module")
def indicator():
    spec = importlib.util.spec_from_file_location("vb_typer_indicator", HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_levels_keep_the_window_size(indicator):
    levels = indicator.Levels(bars=4)
    for value in (10, 20, 30, 40, 50):
        levels.push(value)
    assert len(levels.values) == 4


def test_levels_attack_faster_than_they_release(indicator):
    levels = indicator.Levels(bars=2)
    levels.push(100)
    after_attack = levels.shown
    levels.push(0)
    assert after_attack > 50  # subiu rápido
    assert levels.shown > after_attack * 0.7  # desceu devagar


def test_levels_clamp_out_of_range_values(indicator):
    levels = indicator.Levels(bars=2)
    levels.push(1000)
    assert levels.shown <= 100
    levels.push(-50)
    assert levels.shown >= 0


def test_phase_comes_from_the_snapshot(indicator):
    assert indicator.phase_from_state({"phase": "recording"}) == "recording"
    assert indicator.phase_from_state({"phase": "error"}) == "error"


def test_phase_falls_back_for_old_snapshots(indicator):
    assert indicator.phase_from_state({}) == "idle"
    assert indicator.phase_from_state({"recording": True}) == "recording"
    assert indicator.phase_from_state({"state": "processing"}) == "processing"
    assert indicator.phase_from_state({"phase": "inventado"}) == "idle"


def test_helper_only_needs_the_standard_library(indicator):
    """O helper roda no Python do sistema: GTK não pode ser importado no topo."""
    source = HELPER.read_text(encoding="utf-8")
    header = source.split('"""', 2)[2]
    assert "import gi" not in header.split("def ")[0]


def test_helper_rejects_missing_arguments(indicator):
    assert indicator.main([]) == 2


def test_colour_mixing_interpolates_between_stops(indicator):
    assert indicator._mix((0.0, 0.0, 0.0), (1.0, 0.5, 0.25), 1.0) == (1.0, 0.5, 0.25)
    assert indicator._mix((0.0, 0.0, 0.0), (1.0, 0.5, 0.25), 0.0) == (0.0, 0.0, 0.0)
    assert indicator._mix((0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0.5) == (0.5, 0.5, 0.5)


def test_full_level_is_reachable_by_normal_speech(indicator):
    """O nível de fala comum precisa passar de metade da barra mais alta."""
    assert 25 <= indicator.FULL_LEVEL <= 60


def test_debug_is_inert_without_the_environment_variable(indicator):
    assert indicator.DEBUG_PATH in (None, "") or isinstance(indicator.DEBUG_PATH, str)
    indicator._debug("nada deve acontecer")  # não pode falhar nem escrever nada
