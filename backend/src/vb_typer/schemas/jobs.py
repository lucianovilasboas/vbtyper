"""Esquemas dos jobs de transcrição."""

from __future__ import annotations

from pydantic import BaseModel

from vb_typer.db.models import Job
from vb_typer.domain.enums import JobStatus
from vb_typer.schemas.common import IsoStamp, ORMModel
from vb_typer.schemas.transcriptions import TranscriptionRead


class JobRead(ORMModel):
    id: str
    status: JobStatus
    phase: str = ""
    created_at: IsoStamp
    updated_at: IsoStamp
    started_at: IsoStamp | None = None
    finished_at: IsoStamp | None = None
    model: str
    language: str
    mode: str
    profile: str
    filename: str
    content_type: str
    size_bytes: int
    duration_s: float
    error: str | None = None
    transcription_id: int | None = None
    result: TranscriptionRead | None = None


class JobPage(BaseModel):
    items: list[JobRead]
    total: int


def job_to_read(job: Job, transcription=None) -> JobRead:
    data = JobRead.model_validate(job)
    if transcription is not None:
        data = data.model_copy(update={"result": TranscriptionRead.model_validate(transcription)})
    return data
