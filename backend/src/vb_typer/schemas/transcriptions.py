"""Esquemas do histórico de transcrições."""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field

from vb_typer.domain.pricing import cost_usd
from vb_typer.schemas.common import IsoStamp, ORMModel


class VersionRead(ORMModel):
    id: int
    profile: str
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    created_at: IsoStamp
    error: str | None = None


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
    profile: str = "literal"
    raw_text: str | None = None
    transcribe_ms: int
    insert_ms: int
    inserted: bool
    error: str | None = None
    # Ditados anteriores usados como contexto de continuidade (0 = nenhum).
    continuity_count: int = 0
    # Destino de entrega e ferramentas efetivas aplicadas ao texto.
    delivery: str = "text"
    tools: list[str] = []
    # Só o detalhe preenche as versões; a lista fica leve.
    versions: list[VersionRead] = []

    @computed_field
    @property
    def cost_usd(self) -> float:
        """Custo estimado do áudio deste ditado, pela tarifa do modelo usado."""
        return round(cost_usd(self.model, self.duration_s), 6)


def transcription_read(row, versions=None) -> TranscriptionRead:
    """Transcrição + versões editoriais (quando pedidas)."""
    data = TranscriptionRead.model_validate(row)
    if versions:
        data = data.model_copy(
            update={"versions": [VersionRead.model_validate(item) for item in versions]}
        )
    return data


class RenderRequest(BaseModel):
    profile: str = Field(min_length=1, max_length=40)


class TranscriptionPage(BaseModel):
    items: list[TranscriptionRead]
    total: int
    limit: int
    offset: int


class TranscriptionInsertPatch(BaseModel):
    inserted: bool
    insert_ms: int | None = Field(default=None, ge=0)
