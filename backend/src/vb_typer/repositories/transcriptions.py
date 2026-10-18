"""Repositório de transcrições (acesso SQL)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from vb_typer.db.models import Transcription


@dataclass(frozen=True)
class TranscriptionFilter:
    date_from: str | None = None
    date_to: str | None = None
    model: str | None = None
    inserted: bool | None = None
    search: str | None = None


def _apply(stmt, filters: TranscriptionFilter):
    if filters.date_from:
        stmt = stmt.where(Transcription.created_at >= filters.date_from)
    if filters.date_to:
        stmt = stmt.where(Transcription.created_at <= filters.date_to)
    if filters.model:
        stmt = stmt.where(Transcription.model == filters.model)
    if filters.inserted is not None:
        stmt = stmt.where(Transcription.inserted.is_(filters.inserted))
    if filters.search:
        pattern = f"%{filters.search}%"
        stmt = stmt.where(
            or_(Transcription.text.ilike(pattern), Transcription.error.ilike(pattern))
        )
    return stmt


class TranscriptionRepository:
    def list(
        self, session: Session, filters: TranscriptionFilter, limit: int, offset: int
    ) -> tuple[list[Transcription], int]:
        base = _apply(select(Transcription), filters)
        total = session.scalar(_apply(select(func.count(Transcription.id)), filters)) or 0
        items = session.scalars(
            base.order_by(Transcription.id.desc()).limit(limit).offset(offset)
        ).all()
        return list(items), int(total)

    def all(self, session: Session, filters: TranscriptionFilter) -> list[Transcription]:
        stmt = _apply(select(Transcription), filters).order_by(Transcription.id.asc())
        return list(session.scalars(stmt).all())

    def get(self, session: Session, transcription_id: int) -> Transcription | None:
        return session.get(Transcription, transcription_id)

    def add(self, session: Session, transcription: Transcription) -> Transcription:
        session.add(transcription)
        session.flush()
        return transcription

    def delete(self, session: Session, transcription: Transcription) -> None:
        session.delete(transcription)

    def find_legacy(self, session: Session, source: str, legacy_id: int) -> Transcription | None:
        return session.scalar(
            select(Transcription).where(
                Transcription.legacy_source == source,
                Transcription.legacy_id == legacy_id,
            )
        )
