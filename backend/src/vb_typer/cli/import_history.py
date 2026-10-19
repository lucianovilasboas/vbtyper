"""Importa o histórico do app 1.x (SQLite ``history.db``) para o backend 2.x.

A leitura é somente-leitura (``mode=ro``): o banco da versão 1.x nunca é
alterado. A importação é idempotente — cada linha guarda ``legacy_source`` e
``legacy_id`` e é ignorada se já tiver sido importada.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from vb_typer.api.deps import build_container
from vb_typer.core.config import get_settings
from vb_typer.core.paths import ensure_paths, resolve_paths, secure_file
from vb_typer.db import migrate
from vb_typer.repositories.transcriptions import TranscriptionRepository

LEGACY_COLUMNS = (
    "id",
    "created_at",
    "audio_path",
    "audio_bytes",
    "duration_s",
    "text",
    "words",
    "model",
    "language",
    "transcribe_ms",
    "insert_ms",
    "inserted",
    "error",
)


@dataclass
class ImportReport:
    imported: int = 0
    skipped: int = 0
    audio_copied: int = 0
    audio_reused: int = 0
    audio_missing: int = 0
    errors: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            f"Importadas: {self.imported}",
            f"Ignoradas (já existiam): {self.skipped}",
            f"Áudios copiados: {self.audio_copied}",
            f"Áudios já no lugar (não duplicados): {self.audio_reused}",
            f"Áudios ausentes: {self.audio_missing}",
        ]
        if self.errors:
            lines.append(f"Erros: {len(self.errors)}")
            lines.extend(f"  - {item}" for item in self.errors[:10])
        return "\n".join(lines)


def _resolve_source(value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_dir():
        path = path / "history.db"
    if not path.is_file():
        raise FileNotFoundError(f"Banco de origem não encontrado: {path}")
    return path


def _legacy_columns(connection: sqlite3.Connection) -> list[str]:
    available = {row[1] for row in connection.execute("PRAGMA table_info(transcriptions)")}
    return [column for column in LEGACY_COLUMNS if column in available]


def _same_file(first: Path, second: Path) -> bool:
    try:
        return os.path.samefile(first, second)
    except OSError:
        return False


def _copy_audio(
    source: Path, audio_root: Path, moment: time.struct_time | None
) -> tuple[Path, bool] | None:
    """Leva o áudio para o diretório do 2.x; devolve ``(caminho, houve_cópia)``.

    ``None`` quando o arquivo de origem não existe. No Linux o app 1.x grava no
    *mesmo* diretório de áudio do 2.x: nesse caso o arquivo já está no lugar e é
    referenciado, em vez de duplicado com sufixo ``-1``.
    """
    if not source.is_file():
        return None
    stamp = moment or time.localtime(source.stat().st_mtime)
    folder = audio_root / time.strftime("%Y", stamp) / time.strftime("%m", stamp)
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / source.name
    if destination.exists() and _same_file(source, destination):
        return destination, False
    if destination.exists():
        counter = 1
        while True:
            candidate = folder / f"{source.stem}-{counter}{source.suffix}"
            if not candidate.exists():
                destination = candidate
                break
            counter += 1
    shutil.copy2(source, destination)
    with contextlib.suppress(OSError):
        destination.chmod(0o600)
    return destination, True


def run_import(
    *,
    source: Path,
    audio_dir: Path | None,
    database: Path,
    dry_run: bool = False,
) -> ImportReport:
    report = ImportReport()
    connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        columns = _legacy_columns(connection)
        if "id" not in columns or "created_at" not in columns:
            raise RuntimeError(
                "O arquivo não parece ser um history.db do VB Typer 1.x (faltam colunas esperadas)."
            )
        select = ", ".join(columns)
        rows = connection.execute(
            f"SELECT {select} FROM transcriptions ORDER BY id"  # noqa: S608 - colunas fixas
        ).fetchall()
    finally:
        connection.close()

    if dry_run:
        report.imported = len(rows)
        return report

    settings = get_settings()
    paths = ensure_paths(resolve_paths(settings))
    target = database or paths.database
    migrate.upgrade(target)
    secure_file(target)
    container = build_container(settings, paths)
    audio_root = audio_dir or paths.audio_dir
    source_key = str(source.resolve())
    repo = TranscriptionRepository()

    with container.session_factory() as session:
        for row in rows:
            data = dict(row)
            legacy_id = int(data["id"])
            if repo.find_legacy(session, source_key, legacy_id) is not None:
                report.skipped += 1
                continue
            copied: Path | None = None
            raw_audio = data.get("audio_path")
            if raw_audio:
                candidate = Path(str(raw_audio)).expanduser()
                if not candidate.is_file() and audio_dir is not None:
                    candidate = Path(audio_dir) / candidate.name
                try:
                    moment = time.strptime(str(data["created_at"]), "%Y-%m-%d %H:%M:%S")
                except (ValueError, KeyError):
                    moment = None
                result = _copy_audio(candidate, audio_root, moment)
                if result is None:
                    report.audio_missing += 1
                else:
                    copied, copied_now = result
                    if copied_now:
                        report.audio_copied += 1
                    else:
                        report.audio_reused += 1
            try:
                container.history.record(
                    text=str(data.get("text") or ""),
                    duration_s=float(data.get("duration_s") or 0.0),
                    model=str(data.get("model") or ""),
                    language=str(data.get("language") or ""),
                    audio_path=copied,
                    audio_bytes=int(data.get("audio_bytes") or 0),
                    transcribe_ms=int(data.get("transcribe_ms") or 0),
                    insert_ms=int(data.get("insert_ms") or 0),
                    inserted=bool(data.get("inserted")),
                    error=data.get("error"),
                    created_at=str(data["created_at"]),
                    legacy_source=source_key,
                    legacy_id=legacy_id,
                )
            except Exception as exc:  # pragma: no cover - defensivo
                report.errors.append(f"id {legacy_id}: {exc}")
                continue
            report.imported += 1
    container.engine.dispose()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vb-typer-import",
        description="Importa o histórico do VB Typer 1.x para o backend 2.x.",
    )
    parser.add_argument("--source", required=True, help="history.db do app 1.x (ou seu diretório)")
    parser.add_argument("--audio-dir", default=None, help="diretório de áudios do app 1.x")
    parser.add_argument("--database", default=None, help="banco de destino")
    parser.add_argument("--dry-run", action="store_true", help="apenas contar, sem gravar")
    args = parser.parse_args(argv)

    try:
        source = _resolve_source(args.source)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    audio_dir = Path(args.audio_dir).expanduser() if args.audio_dir else None
    database = Path(args.database).expanduser() if args.database else None
    try:
        report = run_import(
            source=source, audio_dir=audio_dir, database=database, dry_run=args.dry_run
        )
    except Exception as exc:
        print(f"Falha na importação: {exc}", file=sys.stderr)
        return 1
    print(report.render())
    return 0 if not report.errors else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
