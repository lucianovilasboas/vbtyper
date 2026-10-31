"""Preferências do cliente desktop: padrões, validação e ida-e-volta."""

from __future__ import annotations

import json

from vb_typer_desktop import preferences

VALID = {
    "notices": "balloons",
    "anchor": "pointer",
    "position": "top-center",
    "sound": True,
    "size": 64,
}


def test_defaults_show_the_indicator_without_sound():
    current = preferences.Preferences()
    assert current.shows_indicator is True
    assert current.shows_routine_balloons is False
    assert current.shows_error_balloons is True
    assert current.sound is False


def test_balloons_mode_restores_the_old_behaviour():
    current = preferences.from_mapping({"notices": "balloons"})
    assert current.shows_routine_balloons is True
    assert current.shows_indicator is False


def test_none_mode_silences_everything():
    current = preferences.from_mapping({"notices": "none"})
    assert not current.shows_indicator
    assert not current.shows_routine_balloons
    assert not current.shows_error_balloons


def test_both_mode_shows_both():
    current = preferences.from_mapping({"notices": "both"})
    assert current.shows_indicator and current.shows_routine_balloons


def test_invalid_values_fall_back_to_defaults():
    current = preferences.from_mapping(
        {
            "notices": "gritaria",
            "anchor": "lua",
            "position": "canto",
            "sound": "sim",
            "size": 5000,
        }
    )
    assert current == preferences.Preferences()


def test_broken_size_is_ignored():
    assert preferences.from_mapping({"size": 10}).size == preferences.DEFAULTS["size"]
    assert preferences.from_mapping({"size": True}).size == preferences.DEFAULTS["size"]
    assert preferences.from_mapping({"size": "40"}).size == preferences.DEFAULTS["size"]


def test_tuning_defaults_and_bounds():
    assert preferences.Preferences().speed == 1.0
    assert preferences.Preferences().sensitivity == 1.0
    assert preferences.from_mapping({"speed": 2.0, "sensitivity": 1.5}).speed == 2.0
    assert preferences.from_mapping({"speed": 99}).speed == preferences.MAX_TUNING
    assert preferences.from_mapping({"speed": 0}).speed == preferences.MIN_TUNING
    assert preferences.from_mapping({"speed": "rápido"}).speed == 1.0
    assert preferences.from_mapping({"sensitivity": True}).sensitivity == 1.0


def test_shape_defaults_to_the_web_wave_and_accepts_the_bar():
    assert preferences.Preferences().shape == "wave"
    assert preferences.from_mapping({"shape": "bar"}).shape == "bar"
    assert preferences.from_mapping({"shape": "triangulo"}).shape == "wave"
    assert preferences.SHAPES == ("bar", "wave")


def test_non_mapping_input_is_ignored():
    assert preferences.from_mapping(["nada"]) == preferences.Preferences()


def test_latency_defaults_are_the_fast_ones():
    current = preferences.Preferences()
    # Modelo vazio = segue o servidor: a web e a bandeja mandam no ditado.
    assert current.stt_model == ""
    assert current.upload_format == "auto"
    # O ritmo da inserção é o comprovado: uma tecla por vez, com folga para o
    # método de entrada commitar em ordem.
    assert (current.typing_batch, current.typing_delay_ms) == (1, 4)
    assert current.typing_delay == 0.004


def test_typing_rhythm_is_bounded_and_typed():
    assert preferences.from_mapping({"typing_batch": 8}).typing_batch == 8
    assert preferences.from_mapping({"typing_batch": 0}).typing_batch == preferences.MIN_BATCH
    assert preferences.from_mapping({"typing_batch": 999}).typing_batch == preferences.MAX_BATCH
    assert (
        preferences.from_mapping({"typing_batch": "16"}).typing_batch
        == (preferences.DEFAULTS["typing_batch"])
    )
    assert (
        preferences.from_mapping({"typing_batch": True}).typing_batch
        == (preferences.DEFAULTS["typing_batch"])
    )
    assert preferences.from_mapping({"typing_delay_ms": 4}).typing_delay == 0.004
    assert preferences.from_mapping({"typing_delay_ms": 90}).typing_delay_ms == (
        preferences.MAX_TYPING_DELAY_MS
    )
    assert preferences.from_mapping({"typing_delay_ms": -3}).typing_delay_ms == 0


def test_upload_format_accepts_only_known_choices():
    assert preferences.from_mapping({"upload_format": "opus"}).upload_format == "opus"
    assert preferences.from_mapping({"upload_format": "wav"}).upload_format == "wav"
    assert preferences.from_mapping({"upload_format": "ogg"}).upload_format == "auto"


def test_the_stt_model_can_be_left_to_the_server():
    # Vazio é o padrão: segue o modelo escolhido no servidor.
    assert preferences.from_mapping({"stt_model": ""}).stt_model == ""
    assert preferences.from_mapping({"stt_model": "  "}).stt_model == ""
    assert preferences.from_mapping({"stt_model": 7}).stt_model == ""
    assert preferences.from_mapping({"stt_model": " gpt-transcribe "}).stt_model == "gpt-transcribe"


def test_load_without_file_uses_defaults(tmp_path):
    assert preferences.load(tmp_path / "nao-existe.json") == preferences.Preferences()


def test_load_ignores_corrupted_file(tmp_path):
    target = tmp_path / "desktop.json"
    target.write_text("{ isso não é json", encoding="utf-8")
    assert preferences.load(target) == preferences.Preferences()


def test_save_and_load_round_trip(tmp_path):
    target = tmp_path / "config" / "desktop.json"
    saved = preferences.Preferences(**VALID)
    assert preferences.save(saved, target) == target
    assert preferences.load(target) == saved
    assert json.loads(target.read_text(encoding="utf-8"))["notices"] == "balloons"


def test_preference_file_follows_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert preferences.preference_file() == tmp_path / "vb-typer" / "desktop.json"
