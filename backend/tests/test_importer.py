"""Importação do histórico do app 1.x."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from vb_typer.cli.import_history import run_import
from vb_typer.core.config import get_settings

LEGACY_SCHEMA = """
CREATE TABLE IF NOT EXISTS transcriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    audio_path TEXT,
    audio_bytes INTEGER NOT NULL DEFAULT 0,
    duration_s REAL NOT NULL DEFAULT 0,
    text TEXT NOT NULL DEFAULT '',
    words INTEGER NOT NULL DEFAULT 0,
    model TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT '',
    transcribe_ms INTEGER NOT NULL DEFAULT 0,
    insert_ms INTEGER NOT NULL DEFAULT 0,
    inserted INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
"""


@pytest.fixture
def temp_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VB_TYPER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("VB_TYPER_CONFIG_DIR", str(tmp_path / "cfg"))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def _build_legacy(root: Path, make_wav) -> tuple[Path, Path]:
    legacy = root / "legacy" / "history.db"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    audio = root / "legacy" / "audio" / "2026" / "01" / "captura.wav"
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(make_wav(1.5))

    connection = sqlite3.connect(legacy)
    connection.executescript(LEGACY_SCHEMA)
    connection.execute(
        "INSERT INTO transcriptions (created_at, audio_path, audio_bytes, duration_s, text,"
        " words, model, language, transcribe_ms, inserted) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            "2026-01-05 09:00:00",
            str(audio),
            audio.stat().st_size,
            1.5,
            "primeiro ditado",
            2,
            "gpt-transcribe",
            "pt",
            1200,
            1,
        ),
    )
    connection.execute(
        "INSERT INTO transcriptions (created_at, duration_s, text, words, model, language,"
        " inserted, error) VALUES (?,?,?,?,?,?,?,?)",
        ("2026-01-06 10:00:00", 0.5, "", 0, "gpt-4o-mini-transcribe", "pt", 0, "Gravador falhou"),
    )
    connection.commit()
    connection.close()
    return legacy, audio


def test_import_is_idempotent_and_copies_audio(temp_settings, make_wav):
    legacy, audio = _build_legacy(temp_settings, make_wav)
    target = temp_settings / "data" / "vb-typer.db"

    first = run_import(source=legacy, audio_dir=None, database=target)
    assert first.imported == 2
    assert first.skipped == 0
    assert first.audio_copied == 1
    assert first.audio_reused == 0
    assert first.audio_missing == 0
    assert not first.errors

    second = run_import(source=legacy, audio_dir=None, database=target)
    assert second.imported == 0
    assert second.skipped == 2

    connection = sqlite3.connect(target)
    try:
        rows = connection.execute(
            "SELECT id, created_at, text, duration_s, inserted, error, audio_path"
            " FROM transcriptions ORDER BY id"
        ).fetchall()
    finally:
        connection.close()
    assert len(rows) == 2
    assert rows[0][2] == "primeiro ditado"
    assert rows[0][6] and Path(rows[0][6]).is_file()
    assert rows[0][6] != str(audio)
    # A pasta do áudio segue a data do ditado (2026-01), não o mtime da cópia.
    assert Path(rows[0][6]).parent.parent.name == "2026"
    assert Path(rows[0][6]).parent.name == "01"
    assert rows[1][5] == "Gravador falhou"


def test_source_database_is_opened_read_only(temp_settings, make_wav):
    legacy, _ = _build_legacy(temp_settings, make_wav)
    before = legacy.read_bytes()
    run_import(source=legacy, audio_dir=None, database=temp_settings / "data" / "vb-typer.db")
    assert legacy.read_bytes() == before


def test_audio_already_in_place_is_not_duplicated(temp_settings, make_wav):
    """No Linux o 1.x grava no mesmo diretório do 2.x: referenciar, não duplicar."""
    data_dir = temp_settings / "data"
    audio = data_dir / "audio" / "2026" / "01" / "ja-no-lugar.wav"
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(make_wav(1.0))

    legacy = temp_settings / "legacy" / "history.db"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(legacy)
    connection.executescript(LEGACY_SCHEMA)
    connection.execute(
        "INSERT INTO transcriptions (created_at, audio_path, audio_bytes, duration_s, text,"
        " model, language, inserted) VALUES (?,?,?,?,?,?,?,?)",
        (
            "2026-01-05 09:00:00",
            str(audio),
            audio.stat().st_size,
            1.0,
            "já estava aqui",
            "gpt-transcribe",
            "pt",
            1,
        ),
    )
    connection.commit()
    connection.close()

    report = run_import(source=legacy, audio_dir=None, database=data_dir / "vb-typer.db")
    assert report.imported == 1
    assert report.audio_copied == 0
    assert report.audio_reused == 1

    connection = sqlite3.connect(data_dir / "vb-typer.db")
    try:
        stored = connection.execute("SELECT audio_path FROM transcriptions").fetchone()[0]
    finally:
        connection.close()
    assert Path(stored) == audio
    assert len(list(audio.parent.glob("*.wav"))) == 1


def test_dry_run_does_not_create_target(temp_settings, make_wav):
    legacy, _ = _build_legacy(temp_settings, make_wav)
    target = temp_settings / "data" / "vb-typer.db"
    report = run_import(source=legacy, audio_dir=None, database=target, dry_run=True)
    assert report.imported == 2
    assert not target.exists()


def test_old_schema_without_words_column(temp_settings, make_wav):
    legacy = temp_settings / "old" / "history.db"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(legacy)
    connection.executescript(
        """
        CREATE TABLE transcriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            audio_path TEXT,
            audio_bytes INTEGER NOT NULL DEFAULT 0,
            duration_s REAL NOT NULL DEFAULT 0,
            text TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            language TEXT NOT NULL DEFAULT '',
            transcribe_ms INTEGER NOT NULL DEFAULT 0,
            insert_ms INTEGER NOT NULL DEFAULT 0,
            inserted INTEGER NOT NULL DEFAULT 0,
            error TEXT
        );
        """
    )
    connection.execute(
        "INSERT INTO transcriptions (created_at, duration_s, text, model, language, inserted)"
        " VALUES ('2026-02-01 08:00:00', 2.0, 'sem coluna words', 'gpt-transcribe', 'pt', 1)"
    )
    connection.commit()
    connection.close()

    report = run_import(
        source=legacy, audio_dir=None, database=temp_settings / "data" / "vb-typer.db"
    )
    assert report.imported == 1
    connection = sqlite3.connect(temp_settings / "data" / "vb-typer.db")
    try:
        words = connection.execute("SELECT words FROM transcriptions").fetchone()[0]
    finally:
        connection.close()
    assert words == 3
