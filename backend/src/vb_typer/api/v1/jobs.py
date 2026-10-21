"""Criação, acompanhamento e cancelamento de jobs de transcrição."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, UploadFile, status

from vb_typer.api.deps import ContainerDep, ManagerDep
from vb_typer.db.models import Job
from vb_typer.domain.enums import JobStatus
from vb_typer.domain.errors import AudioTooLargeError
from vb_typer.schemas.jobs import JobPage, JobRead, job_to_read

router = APIRouter(prefix="/transcription-jobs", tags=["transcrição"])

CHUNK_BYTES = 1024 * 1024


async def _read_upload(file: UploadFile, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise AudioTooLargeError(f"O áudio excede o limite de {limit // (1024 * 1024)} MB.")
        chunks.append(chunk)
    return b"".join(chunks)


def _with_result(container: ContainerDep, job: Job) -> JobRead:
    transcription = None
    if job.transcription_id is not None:
        transcription = container.history.get(job.transcription_id)
    return job_to_read(job, transcription)


@router.post("", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    container: ContainerDep,
    manager: ManagerDep,
    file: Annotated[UploadFile, File(description="Áudio a transcrever.")],
    model: Annotated[str | None, Form()] = None,
    language: Annotated[str | None, Form()] = None,
    mode: Annotated[str | None, Form()] = None,
    profile: Annotated[str | None, Form()] = None,
    duration_s: Annotated[float | None, Form(description="Duração medida pelo cliente.")] = None,
) -> JobRead:
    data = await _read_upload(file, container.settings.max_upload_bytes)
    job = await asyncio.to_thread(
        container.transcription.create_job,
        data=data,
        filename=file.filename or "",
        content_type=file.content_type or "",
        model=model,
        language=language,
        mode=mode,
        profile=profile,
        duration_s=duration_s,
    )
    await manager.submit(job.id)
    return job_to_read(job)


@router.get("", response_model=JobPage)
def list_jobs(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    job_status: Annotated[JobStatus | None, Query(alias="status")] = None,
) -> JobPage:
    status_value = job_status.value if job_status else None
    items = container.transcription.list(limit=limit, status=status_value)
    return JobPage(items=[_with_result(container, item) for item in items], total=len(items))


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: str, container: ContainerDep) -> JobRead:
    job = container.transcription.get(job_id)
    return _with_result(container, job)


@router.delete("/{job_id}", response_model=JobRead)
async def cancel_job(job_id: str, container: ContainerDep, manager: ManagerDep) -> JobRead:
    job = await asyncio.to_thread(container.transcription.get, job_id)
    if job.status not in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELED):
        await manager.cancel(job_id)
        job = await asyncio.to_thread(container.transcription.get, job_id)
    return job_to_read(job)
