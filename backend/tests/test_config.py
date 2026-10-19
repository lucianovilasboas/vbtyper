"""Configuração vinda do ambiente (prefixo ``VB_TYPER_``)."""

from __future__ import annotations

from vb_typer.core.config import AppSettings


def test_list_fields_accept_comma_separated_env(monkeypatch):
    """Listas chegam por ambiente no formato separado por vírgula."""
    monkeypatch.setenv("VB_TYPER_ALLOWED_HOSTS", "127.0.0.1, localhost, 10.147.20.5")
    monkeypatch.setenv("VB_TYPER_CORS_ORIGINS", "http://10.147.20.5:8765")
    monkeypatch.setenv("VB_TYPER_ALLOWED_MODELS", "gpt-4o-mini-transcribe,gpt-transcribe")

    settings = AppSettings()

    assert settings.allowed_hosts == ("127.0.0.1", "localhost", "10.147.20.5")
    assert settings.cors_origins == ("http://10.147.20.5:8765",)
    assert settings.allowed_models == ("gpt-4o-mini-transcribe", "gpt-transcribe")


def test_list_fields_still_accept_json_env(monkeypatch):
    monkeypatch.setenv("VB_TYPER_ALLOWED_HOSTS", '["a.example", "b.example"]')

    assert AppSettings().allowed_hosts == ("a.example", "b.example")


def test_empty_list_env_becomes_empty_tuple(monkeypatch):
    monkeypatch.setenv("VB_TYPER_CORS_ORIGINS", "")

    assert AppSettings().cors_origins == ()


def test_single_item_env_is_not_split_by_character(monkeypatch):
    monkeypatch.setenv("VB_TYPER_ALLOWED_MODELS", "gpt-transcribe")

    assert AppSettings().allowed_models == ("gpt-transcribe",)
