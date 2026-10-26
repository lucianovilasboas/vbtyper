"""Conexão: precedência de URL, token 0600, validação, autostart e integração."""

from __future__ import annotations

import stat
from pathlib import Path

import httpx
import pytest

from vb_typer_desktop import connection, preferences
from vb_typer_desktop.connection import SetupResult


def test_normalize_url_adds_scheme_and_trims_slash():
    assert connection.normalize_url("vbtyper.exemplo.com") == "https://vbtyper.exemplo.com"
    assert connection.normalize_url("localhost:8765") == "http://localhost:8765"
    assert connection.normalize_url("127.0.0.1:8765/") == "http://127.0.0.1:8765"
    assert connection.normalize_url("https://x.ts.net///") == "https://x.ts.net"
    assert connection.normalize_url("  ") == ""


def test_resolve_base_url_precedence(monkeypatch):
    current = preferences.Preferences(base_url="https://prefs")
    monkeypatch.setenv("VB_TYPER_API_BASE_URL", "https://env")
    assert connection.resolve_base_url("http://cli", current) == "http://cli"
    assert connection.resolve_base_url(None, current) == "https://env"
    monkeypatch.delenv("VB_TYPER_API_BASE_URL")
    assert connection.resolve_base_url(None, current) == "https://prefs"
    assert connection.resolve_base_url(None, preferences.Preferences()) == ("http://127.0.0.1:8765")


def test_packaged_default_is_the_public_domain(monkeypatch):
    monkeypatch.setenv("APPIMAGE", "/tmp/VB-Typer.AppImage")
    assert connection.default_base_url() == connection.PACKAGED_DEFAULT_URL
    monkeypatch.delenv("APPIMAGE")
    assert connection.default_base_url() == "http://127.0.0.1:8765"


def test_save_token_creates_a_0600_file():
    assert connection.stored_token() is None
    target = connection.save_token("segredo")
    assert target == connection.token_file()
    assert connection.stored_token() == "segredo"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_has_token_prefers_the_environment(monkeypatch):
    assert connection.has_token() is False
    connection.save_token("do-arquivo")
    assert connection.has_token() is True
    monkeypatch.setenv("VB_TYPER_API_TOKEN", "do-ambiente")
    assert connection.has_token() is True


def test_save_connection_preserves_other_preferences():
    preferences.save(preferences.Preferences(notices="balloons"))
    connection.save_connection("https://vbtyper.exemplo.com/", "token")
    current = preferences.load()
    assert current.base_url == "https://vbtyper.exemplo.com"
    assert current.notices == "balloons"
    assert connection.stored_token() == "token"


def test_save_connection_without_a_new_token_keeps_the_current_one():
    connection.save_token("antigo")
    connection.save_connection("https://outro.exemplo.com", "")
    assert connection.stored_token() == "antigo"
    assert preferences.load().base_url == "https://outro.exemplo.com"


def test_save_connection_rejects_an_empty_url():
    with pytest.raises(ValueError):
        connection.save_connection("   ", "token")


def test_probe_accepts_a_valid_token(respx_mock):
    route = respx_mock.get("http://127.0.0.1:8765/api/v1/settings").mock(
        return_value=httpx.Response(200, json={"model": "x"})
    )
    ok, message = connection.probe("http://127.0.0.1:8765", "token")
    assert ok is True
    assert "ok" in message
    assert route.called


def test_probe_explains_a_rejected_token(respx_mock):
    respx_mock.get("http://127.0.0.1:8765/api/v1/settings").mock(
        return_value=httpx.Response(401, json={})
    )
    ok, message = connection.probe("http://127.0.0.1:8765", "token")
    assert ok is False
    assert "recusado" in message


def test_probe_reports_a_network_failure(respx_mock):
    respx_mock.get("http://127.0.0.1:8765/api/v1/settings").mock(
        side_effect=httpx.ConnectError("sem rede")
    )
    ok, message = connection.probe("http://127.0.0.1:8765", "token")
    assert ok is False
    assert "conectar" in message


def test_probe_requires_a_url_and_token():
    assert connection.probe("", "token")[0] is False
    assert connection.probe("http://127.0.0.1:8765", "")[0] is False


def test_autostart_entry_and_removal():
    target = connection.install_autostart("/usr/bin/vb-typer")
    text = target.read_text(encoding="utf-8")
    assert "Exec=/usr/bin/vb-typer" in text
    assert "X-GNOME-Autostart-enabled=true" in text
    assert connection.autostart_installed() is True
    connection.install_autostart("/caminho com espaço/vb-typer")
    assert 'Exec="/caminho com espaço/vb-typer"' in target.read_text(encoding="utf-8")
    connection.remove_autostart()
    assert connection.autostart_installed() is False


def test_install_appimage_copies_to_a_stable_path(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    source = tmp_path / "download" / "VB-Typer-1.2.3.AppImage"
    source.parent.mkdir()
    source.write_bytes(b"appimage")
    target = connection.install_appimage(source)
    assert target == tmp_path / ".local" / "bin" / connection.STABLE_APPIMAGE
    assert target.read_bytes() == b"appimage"
    assert stat.S_IMODE(target.stat().st_mode) == 0o755
    assert connection.install_appimage(target) == target


def test_menu_entry_and_icon(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    target = connection.write_menu_entry(str(tmp_path / "bin" / "VB-Typer.AppImage"))
    text = target.read_text(encoding="utf-8")
    assert "Exec=" in text and "VB-Typer.AppImage" in text
    icon = tmp_path / "share" / "icons" / "hicolor" / "256x256" / "apps" / "vb-typer.png"
    assert icon.is_file()


def test_configure_interactively_saves_and_integrates(monkeypatch):
    calls = []
    monkeypatch.setattr(
        connection,
        "run_setup_dialog",
        lambda *a, **k: SetupResult("https://novo.exemplo.com", "novo", True),
    )
    monkeypatch.setattr(connection, "install_integration", lambda: calls.append("install"))
    result = connection.configure_interactively("https://antigo", preferences.Preferences())
    assert result is not None
    assert connection.stored_token() == "novo"
    assert preferences.load().base_url == "https://novo.exemplo.com"
    assert calls == ["install"]


def test_configure_interactively_cancel_changes_nothing(monkeypatch):
    monkeypatch.setattr(connection, "run_setup_dialog", lambda *a, **k: None)
    assert connection.configure_interactively("https://antigo", preferences.Preferences()) is None
    assert connection.stored_token() is None


def test_setup_dialog_without_gtk_reports_the_reason(monkeypatch, capsys):
    monkeypatch.setattr(connection, "gtklib_available", lambda: False)
    assert connection.run_setup_dialog("http://127.0.0.1:8765") is None
    assert "GTK3" in capsys.readouterr().err


def test_preferences_roundtrip_keeps_base_url(tmp_path):
    target = Path(tmp_path) / "desktop.json"
    saved = preferences.Preferences(base_url="https://vbtyper.exemplo.com")
    preferences.save(saved, target)
    assert preferences.load(target).base_url == "https://vbtyper.exemplo.com"
