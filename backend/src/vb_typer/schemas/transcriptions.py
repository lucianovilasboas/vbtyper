"""Esquemas do histórico de transcrições."""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field

from vb_typer.domain.pricing import cost_usd
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
    mode: str = "literal"
    raw_text: str | None = None
    transcribe_ms: int
    insert_ms: int
    inserted: bool
    error: str | None = None

    @computed_field
    @property
    def cost_usd(self) -> float:
        """Custo estimado deste ditado, pela tarifa do modelo usado."""
        return round(cost_usd(self.model, self.duration_s), 6)


class TranscriptionPage(BaseModel):
    items: list[TranscriptionRead]
    total: int
    limit: int
    offset: int


class TranscriptionInsertPatch(BaseModel):
    inserted: bool
    insert_ms: int | None = Field(default=None, ge=0)
