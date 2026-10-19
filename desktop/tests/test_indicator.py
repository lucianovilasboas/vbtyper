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


def test_attack_is_faster_than_release(indicator):
    """Subir reage mais rápido que descer — mas os dois lados são rápidos."""
    levels = indicator.Levels(bars=2)
    levels.push(100, elapsed=0.04)
    rise = levels.shown / 100
    levels.push(0, elapsed=0.04)
    fall = 1 - levels.shown / 100
    assert rise > fall
    assert rise > 0.5 and fall > 0.3


def test_attack_reaches_the_target_almost_immediately(indicator):
    """Uma fala que começa tem de aparecer na hora, não em meio segundo."""
    levels = indicator.Levels(bars=2)
    levels.push(60, elapsed=0.06)
    assert levels.shown > 60 * 0.75


def test_release_falls_quickly_after_the_voice_stops(indicator):
    """Ao parar de falar, a onda cai — o antigo era ~330 ms de constante."""
    levels = indicator.Levels(bars=2)
    levels.push(60, elapsed=0.5)
    assert levels.shown > 59
    for _ in range(4):  # ~160 ms
        levels.push(0, elapsed=0.04)
    assert levels.shown < 15


def test_timing_is_independent_of_the_frame_rate(indicator):
    """Meia dúzia de quadros curtos vale o mesmo que um quadro longo."""
    short, long = indicator.Levels(bars=2), indicator.Levels(bars=2)
    for _ in range(10):
        short.push(80, elapsed=0.01)
    long.push(80, elapsed=0.10)
    assert abs(short.shown - long.shown) < 4


def test_higher_speed_reacts_faster(indicator):
    slow = indicator.Levels(attack_s=indicator.ATTACK_S, release_s=indicator.RELEASE_S)
    fast = indicator.Levels(attack_s=indicator.ATTACK_S / 2, release_s=indicator.RELEASE_S / 2)
    slow.push(70, elapsed=0.04)
    fast.push(70, elapsed=0.04)
    assert fast.shown > slow.shown


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
    assert 20 <= indicator.FULL_LEVEL <= 45


def test_gamma_lifts_the_middle_range(indicator):
    """A curva tem de levantar o meio (fala normal), não achatar os extremos."""
    assert 0.5 <= indicator.GAMMA <= 1.0
    middle = (15.0 / indicator.FULL_LEVEL) ** indicator.GAMMA
    linear = 15.0 / indicator.FULL_LEVEL
    assert middle > linear
    assert middle < 1.0


def test_tuning_is_parsed_and_clamped(indicator):
    assert indicator._tuning("2", 1.0) == 2.0
    assert indicator._tuning("nao-numero", 1.0) == 1.0
    assert indicator._tuning("99", 1.0) == 3.0
    assert indicator._tuning("0", 1.0) == 0.5


def test_main_needs_the_socket(indicator):
    assert indicator.main([]) == 2
    assert indicator.main(["--speed=2"]) == 2


def test_debug_is_inert_without_the_environment_variable(indicator):
    assert indicator.DEBUG_PATH in (None, "") or isinstance(indicator.DEBUG_PATH, str)
    indicator._debug("nada deve acontecer")  # não pode falhar nem escrever nada
