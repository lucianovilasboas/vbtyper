"""Consultas e manutenção do histórico de transcrições."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from vb_typer.adapters.audio_store import AudioStore
from vb_typer.core.config import AppSettings
from vb_typer.db.models import Transcription
from vb_typer.domain.errors import NotFoundError
from vb_typer.repositories.transcriptions import TranscriptionFilter, TranscriptionRepository
from vb_typer.services.common import new_transcription


class HistoryService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: AppSettings,
        audio_store: AudioStore,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.audio_store = audio_store
        self.repo = TranscriptionRepository()

    def record(
        self,
        *,
        text: str,
        duration_s: float,
        model: str,
        language: str,
        mode: str = "literal",
        profile: str = "literal",
        raw_text: str | None = None,
        audio_path: str | Path | None = None,
        audio_bytes: int = 0,
        transcribe_ms: int = 0,
        insert_ms: int = 0,
        inserted: bool = False,
        error: str | None = None,
        created_at: str | None = None,
        legacy_source: str | None = None,
        legacy_id: int | None = None,
        keep_audio: bool | None = None,
    ) -> Transcription:
        keep = self.settings.keep_audio if keep_audio is None else keep_audio
        with self.session_factory() as session:
            row = new_transcription(
                text=text,
                duration_s=duration_s,
                model=model,
                language=language,
                mode=mode,
                profile=profile,
                raw_text=raw_text,
                audio_path=audio_path if keep else None,
                audio_bytes=audio_bytes,
                transcribe_ms=transcribe_ms,
                insert_ms=insert_ms,
                inserted=inserted,
                error=error,
                created_at=created_at,
                legacy_source=legacy_source,
                legacy_id=legacy_id,
            )
            self.repo.add(session, row)
            session.commit()
            session.refresh(row)
            return row

    def list(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        date_from: str | None = None,
        date_to: str | None = None,
        model: str | None = None,
        inserted: bool | None = None,
        search: str | None = None,
    ) -> tuple[list[Transcription], int]:
        filters = TranscriptionFilter(
            date_from=date_from,
            date_to=date_to,
            model=model,
            inserted=inserted,
            search=search,
        )
        with self.session_factory() as session:
            return self.repo.list(session, filters, limit=limit, offset=offset)

    def all(self, **filters) -> list[Transcription]:
        criteria = TranscriptionFilter(**filters)
        with self.session_factory() as session:
            return self.repo.all(session, criteria)

    def get(self, transcription_id: int) -> Transcription:
        with self.session_factory() as session:
            row = self.repo.get(session, transcription_id)
            if row is None:
                raise NotFoundError("Transcrição não encontrada.")
            session.expunge(row)
            return row

    def mark_inserted(
        self, transcription_id: int, *, inserted: bool, insert_ms: int | None = None
    ) -> Transcription:
        with self.session_factory() as session:
            row = self.repo.get(session, transcription_id)
            if row is None:
                raise NotFoundError("Transcrição não encontrada.")
            row.inserted = bool(inserted)
            if insert_ms is not None:
                row.insert_ms = max(0, int(insert_ms))
            session.commit()
            session.refresh(row)
            session.expunge(row)
            return row

    def delete(self, transcription_id: int) -> None:
        with self.session_factory() as session:
            row = self.repo.get(session, transcription_id)
            if row is None:
                raise NotFoundError("Transcrição não encontrada.")
            self.audio_store.delete(row.audio_path)
            self.repo.delete(session, row)
            session.commit()
