"""Histórico: listagem, detalhe, marcação de inserção, exportação e remoção."""

from __future__ import annotations

import csv
import io
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from vb_typer.api.deps import ContainerDep
from vb_typer.core.timeutil import iso_stamp, normalize_bound
from vb_typer.db.models import Transcription
from vb_typer.domain.pricing import cost_usd
from vb_typer.schemas.transcriptions import (
    TranscriptionInsertPatch,
    TranscriptionPage,
    TranscriptionRead,
)

router = APIRouter(prefix="/transcriptions", tags=["histórico"])

CSV_HEADER = [
    "id",
    "created_at",
    "text",
    "words",
    "duration_s",
    "audio_bytes",
    "model",
    "language",
    "cost_usd",
    "transcribe_ms",
    "insert_ms",
    "inserted",
    "error",
]


def _filters(
    date_from: str | None,
    date_to: str | None,
    model: str | None,
    inserted: bool | None,
    search: str | None,
) -> dict:
    return {
        "date_from": normalize_bound(date_from),
        "date_to": normalize_bound(date_to, upper=True),
        "model": model,
        "inserted": inserted,
        "search": search,
    }


@router.get("", response_model=TranscriptionPage)
def list_transcriptions(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    date_from: Annotated[str | None, Query(alias="from")] = None,
    date_to: Annotated[str | None, Query(alias="to")] = None,
    model: str | None = None,
    inserted: bool | None = None,
    search: Annotated[str | None, Query(alias="q")] = None,
) -> TranscriptionPage:
    items, total = container.history.list(
        limit=limit,
        offset=offset,
        **_filters(date_from, date_to, model, inserted, search),
    )
    return TranscriptionPage(
        items=[TranscriptionRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/export.csv")
def export_csv(
    container: ContainerDep,
    date_from: Annotated[str | None, Query(alias="from")] = None,
    date_to: Annotated[str | None, Query(alias="to")] = None,
    model: str | None = None,
    inserted: bool | None = None,
    search: Annotated[str | None, Query(alias="q")] = None,
) -> Response:
    """CSV com BOM e separador ``;`` para abrir direto no Excel pt-BR."""
    rows: list[Transcription] = container.history.all(
        **_filters(date_from, date_to, model, inserted, search)
    )
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(CSV_HEADER)
    for row in rows:
        writer.writerow(
            [
                row.id,
                iso_stamp(row.created_at),
                row.text,
                row.words,
                f"{row.duration_s:.3f}",
                row.audio_bytes,
                row.model,
                row.language,
                f"{cost_usd(row.model, row.duration_s):.6f}",
                row.transcribe_ms,
                row.insert_ms,
                1 if row.inserted else 0,
                row.error or "",
            ]
        )
    body = "\ufeff" + buffer.getvalue()
    return Response(
        content=body,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="vb-typer-historico.csv"'},
    )


@router.get("/{transcription_id}", response_model=TranscriptionRead)
def get_transcription(transcription_id: int, container: ContainerDep) -> TranscriptionRead:
    return TranscriptionRead.model_validate(container.history.get(transcription_id))


@router.patch("/{transcription_id}", response_model=TranscriptionRead)
def patch_transcription(
    transcription_id: int,
    payload: TranscriptionInsertPatch,
    container: ContainerDep,
) -> TranscriptionRead:
    """O cliente informa se conseguiu inserir o texto e quanto tempo levou."""
    row = container.history.mark_inserted(
        transcription_id, inserted=payload.inserted, insert_ms=payload.insert_ms
    )
    return TranscriptionRead.model_validate(row)


@router.delete("/{transcription_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transcription(transcription_id: int, container: ContainerDep) -> Response:
    container.history.delete(transcription_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
