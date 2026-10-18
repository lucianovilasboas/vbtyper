"""Esquemas do histórico de transcrições."""

from __future__ import annotations

from pydantic import BaseModel, Field

from vb_typer.schemas.common import IsoStamp, ORMModel


class TranscriptionRead(ORMModel):
    id: int
    created_at: IsoStamp
    audio_bytes: int
    duration_s: float
    text: str
    words: int
    model: str
    language: str
    transcribe_ms: int
    insert_ms: int
    inserted: bool
    error: str | None = None


class TranscriptionPage(BaseModel):
    items: list[TranscriptionRead]
    total: int
    limit: int
    offset: int


class TranscriptionInsertPatch(BaseModel):
    inserted: bool
    insert_ms: int | None = Field(default=None, ge=0)
