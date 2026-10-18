"""Funções compartilhadas pelos serviços."""

from __future__ import annotations

from pathlib import Path

from vb_typer.core.timeutil import local_stamp
from vb_typer.db.models import Transcription
from vb_typer.domain.enums import DEFAULT_PRICE_PER_MINUTE, PRICING_PER_MINUTE


def words_of(text: str) -> int:
    return len((text or "").split())


def cost_usd(model: str, duration_s: float) -> float:
    rate = PRICING_PER_MINUTE.get(model, DEFAULT_PRICE_PER_MINUTE)
    return max(0.0, float(duration_s)) / 60.0 * rate


def new_transcription(
    *,
    text: str,
    duration_s: float,
    model: str,
    language: str,
    audio_path: str | Path | None = None,
    audio_bytes: int = 0,
    transcribe_ms: int = 0,
    insert_ms: int = 0,
    inserted: bool = False,
    error: str | None = None,
    created_at: str | None = None,
    legacy_source: str | None = None,
    legacy_id: int | None = None,
) -> Transcription:
    """Monta a linha de histórico sem tocar no banco."""
    return Transcription(
        created_at=created_at or local_stamp(),
        audio_path=str(audio_path) if audio_path else None,
        audio_bytes=int(audio_bytes),
        duration_s=float(duration_s or 0.0),
        text=text or "",
        words=words_of(text),
        model=model,
        language=language,
        transcribe_ms=int(transcribe_ms or 0),
        insert_ms=int(insert_ms or 0),
        inserted=bool(inserted),
        error=error,
        legacy_source=legacy_source,
        legacy_id=legacy_id,
    )
