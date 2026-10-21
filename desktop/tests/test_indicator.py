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


def test_attack_is_faster_than_the_fall(indicator):
    """Subir responde de imediato; descer é firme, mas em linha reta."""
    levels = indicator.Levels(bars=2)
    levels.push(100, elapsed=0.04)
    rise = levels.shown
    levels.push(0, elapsed=0.04)
    fall = rise - levels.shown
    assert rise > 60  # quase instantâneo
    assert fall > 10  # e já desce no primeiro quadro
    assert fall < rise  # mas sem pular de uma vez para o fundo


def test_fall_is_linear(indicator):
    """O ponto do ajuste: cada quadro cai o mesmo tanto, sem cauda exponencial."""
    levels = indicator.Levels(bars=2)
    levels.push(80, elapsed=0.5)
    steps = []
    for _ in range(4):
        levels.push(0, elapsed=0.04)
        steps.append(levels.shown)
    deltas = [80 - steps[0]] + [steps[i] - steps[i + 1] for i in range(len(steps) - 1)]
    assert max(deltas) - min(deltas) < 1.0  # todos os degraus iguais


def test_fall_reaches_the_bottom_quickly(indicator):
    """De 60% ao fundo em menos de ~0,25 s (antes ficava rastejando até 0,4 s)."""
    levels = indicator.Levels(bars=2)
    levels.push(60, elapsed=0.5)
    elapsed = 0.0
    while levels.shown > 0 and elapsed < 1.0:
        levels.push(0, elapsed=0.04)
        elapsed += 0.04
    assert elapsed <= 0.24


def test_fall_snaps_below_the_floor(indicator):
    """Com a voz parada, o resto não fica rastejando: zera de vez."""
    levels = indicator.Levels(bars=2)
    levels.push(2.0, elapsed=0.5)
    levels.push(0, elapsed=0.04)
    assert levels.shown == 0.0


def test_fall_does_not_snap_when_there_is_voice(indicator):
    """O piso vale só para o silêncio; com fala, a barra para no alvo."""
    levels = indicator.Levels(bars=2)
    levels.push(30, elapsed=0.5)
    levels.push(20, elapsed=0.04)
    assert 19.9 <= levels.shown <= 20.1


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


def test_higher_speed_falls_faster(indicator):
    slow = indicator.Levels(attack_s=indicator.ATTACK_S, fall_rate=indicator.FALL_PER_SECOND)
    fast = indicator.Levels(
        attack_s=indicator.ATTACK_S / 2, fall_rate=indicator.FALL_PER_SECOND * 2
    )
    slow.push(70, elapsed=0.5)
    fast.push(70, elapsed=0.5)
    slow.push(0, elapsed=0.04)
    fast.push(0, elapsed=0.04)
    assert fast.shown < slow.shown


def test_timing_is_independent_of_the_frame_rate(indicator):
    """Meia dúzia de quadros curtos vale o mesmo que um quadro longo."""
    short, long = indicator.Levels(bars=2), indicator.Levels(bars=2)
    for _ in range(10):
        short.push(80, elapsed=0.01)
    long.push(80, elapsed=0.10)
    assert abs(short.shown - long.shown) < 4


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


def test_fill_width_is_proportional_with_a_visible_minimum(indicator):
    assert indicator.fill_width(0.0, 120, 12) == 0.0
    assert indicator.fill_width(0.5, 120, 12) == 60.0
    assert indicator.fill_width(1.0, 120, 12) == 120.0
    # Num nível baixinho ainda aparece um traço visível, não um pixel.
    assert indicator.fill_width(0.01, 120, 12) == 12.0
    assert indicator.fill_width(2.0, 120, 12) == 120.0
    assert indicator.fill_width(-1.0, 120, 12) == 0.0


def test_level_ratio_applies_the_calibrated_curve(indicator):
    # Sem Indicador instanciado (não abre janela), o cálculo é replicado aqui.
    full, gamma = indicator.FULL_LEVEL, indicator.GAMMA
    middle = (15.0 / full) ** gamma
    assert 0.3 < middle < 0.9


def test_shape_is_parsed_from_the_command_line(indicator):
    assert indicator.SHAPES == ("bar", "wave")
    # Sem socket não há como abrir janela; só garantimos que não explode.
    assert indicator.main(["--shape=wave"]) == 2
    assert indicator.main(["--shape=inventado"]) == 2


def test_debug_is_inert_without_the_environment_variable(indicator):
    assert indicator.DEBUG_PATH in (None, "") or isinstance(indicator.DEBUG_PATH, str)
    indicator._debug("nada deve acontecer")  # não pode falhar nem escrever nada


# ------------------------------------------------------------------- onda


def test_waveform_from_state_validates_and_limits(indicator):
    samples = indicator.waveform_from_state([0, 300, -5, True, "x", 128])
    assert samples == (0, 255, 0, 128)


def test_waveform_from_state_ignores_other_types(indicator):
    assert indicator.waveform_from_state(None) == ()
    assert indicator.waveform_from_state("nada") == ()
    assert indicator.waveform_from_state([1.5, 20]) == (20,)


def test_waveform_from_state_caps_the_points(indicator):
    samples = indicator.waveform_from_state(list(range(256)) * 4)
    assert len(samples) == indicator.MAX_WAVEFORM_POINTS


def test_waveform_points_use_the_web_scale(indicator):
    points = indicator.waveform_points((0, 128, 255), 300, 100)
    assert [point[0] for point in points] == [0, 100, 200]
    assert [round(point[1]) for point in points] == [0, 50, 100]


def test_waveform_points_of_an_empty_sample(indicator):
    assert indicator.waveform_points((), 300, 100) == ()


def test_wave_palette_is_the_same_as_the_web(indicator):
    stops = indicator.WAVE_GRADIENT_STOPS
    assert len(stops) == 9
    assert stops[0][1] == (155 / 255, 0.0, 47 / 255)
    assert stops[-1][1] == (240 / 255, 65 / 255, 166 / 255)


def test_the_wave_is_the_default_shape(indicator):
    import inspect

    signature = inspect.signature(indicator.Indicator.__init__)
    assert signature.parameters["shape"].default == "wave"
    assert indicator.SHAPES == ("bar", "wave")
