"""Contrato do helper GTK: o resultado é um JSON 0600, sem passar por argv."""

from __future__ import annotations

import importlib.util
import json
import stat
from pathlib import Path

SETUP_HELPER = Path(__file__).resolve().parents[1] / "tray" / "setup.py"


def load_helper():
    spec = importlib.util.spec_from_file_location("vb_typer_setup", SETUP_HELPER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalize_url_matches_the_client_rules():
    setup = load_helper()
    assert setup.normalize_url("vbtyper.exemplo.com") == "https://vbtyper.exemplo.com"
    assert setup.normalize_url("localhost:8765") == "http://localhost:8765"
    assert setup.normalize_url("https://x///") == "https://x"


def test_result_file_is_private_and_contains_the_values(tmp_path):
    setup = load_helper()
    target = tmp_path / "resultado.json"
    setup.write_result(target, "https://vbtyper.exemplo.com/", "  segredo  ", True)
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload == {
        "url": "https://vbtyper.exemplo.com",
        "token": "segredo",
        "autostart": True,
    }
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
