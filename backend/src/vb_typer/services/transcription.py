"""Serviço de transcrição: cria jobs e mantém o estado persistido.

Toda a parte síncrona (banco, disco) vive aqui; a orquestração assíncrona com a
OpenAI fica em ``vb_typer.workers.manager``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from vb_typer.adapters.audio_store import AudioStore
from vb_typer.adapters.secrets import SecretsAdapter
from vb_typer.core.config import TRANSCRIPTION_MODES, AppSettings
from vb_typer.core.timeutil import local_stamp
from vb_typer.db.models import AppSetting, Job
from vb_typer.domain.enums import TERMINAL_STATUSES, JobStatus
from vb_typer.domain.errors import DomainError, InvalidModelError, NotFoundError
from vb_typer.repositories.jobs import JobRepository
from vb_typer.repositories.transcriptions import TranscriptionRepository
from vb_typer.services.common import new_transcription


@dataclass(frozen=True)
class JobContext:
    """Dados necessários para processar um job fora do banco."""

    id: str
    filename: str
    content_type: str
    model: str
    language: str
    mode: str
    duration_s: float
    audio_path: Path | None


class TranscriptionService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: AppSettings,
        audio_store: AudioStore,
        secrets: SecretsAdapter,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.audio_store = audio_store
        self.secrets = secrets
        self.jobs = JobRepository()
        self.transcriptions = TranscriptionRepository()

    # --- criação -----------------------------------------------------------
    def create_job(
        self,
        *,
        data: bytes,
        filename: str,
        content_type: str,
        model: str | None,
        language: str | None,
        mode: str | None = None,
    ) -> Job:
        if model and model not in self.settings.allowed_models:
            raise InvalidModelError(
                f"Modelo inválido. Use um de: {', '.join(self.settings.allowed_models)}."
            )
        language = (language or self.settings.default_language).strip().lower()
        if not 2 <= len(language) <= 16:
            raise DomainError("Idioma inválido.", code="invalid_language")

        stored = self.audio_store.save(data, content_type, filename)
        now = local_stamp()
        with self.session_factory() as session:
            # O modo padrão é a escolha do usuário na interface, não a do ambiente:
            # é ele que decide se o ditado sai literal ou ajustado.
            chosen = (mode or self._default_mode(session)).strip().lower()
            if chosen not in TRANSCRIPTION_MODES:
                raise DomainError(
                    f"Modo inválido. Use um de: {', '.join(TRANSCRIPTION_MODES)}.",
                    code="invalid_mode",
                )
            job = Job(
                id=uuid.uuid4().hex,
                status=JobStatus.QUEUED,
                created_at=now,
                updated_at=now,
                model=model or self.settings.default_model,
                language=language,
                mode=chosen,
                filename=stored.filename,
                content_type=stored.content_type,
                size_bytes=stored.size,
                duration_s=stored.duration_s,
                audio_path=str(stored.path),
            )
            self.jobs.add(session, job)
            session.commit()
            session.refresh(job)
            return job

    def _default_mode(self, session: Session) -> str:
        row = session.get(AppSetting, 1)
        return row.mode if row is not None else self.settings.default_mode

    # --- leitura -----------------------------------------------------------
    def get(self, job_id: str) -> Job:
        with self.session_factory() as session:
            job = self.jobs.get(session, job_id)
            if job is None:
                raise NotFoundError("Job não encontrado.")
            session.expunge(job)
            return job

    def list(self, *, limit: int = 20, status: str | None = None) -> list[Job]:
        with self.session_factory() as session:
            items = self.jobs.list(session, limit=limit, status=status)
            for item in items:
                session.expunge(item)
            return items

    def api_key_present(self) -> bool:
        return self.secrets.has_api_key()

    # --- processamento -----------------------------------------------------
    def claim(self, job_id: str) -> JobContext | None:
        """Marca o job como em execução. Devolve ``None`` se não for executável."""
        with self.session_factory() as session:
            job = self.jobs.get(session, job_id)
            if job is None or job.status != JobStatus.QUEUED:
                return None
            now = local_stamp()
            if job.cancel_requested:
                job.status = JobStatus.CANCELED
                job.finished_at = now
                job.updated_at = now
                self.audio_store.delete(job.audio_path)
                job.audio_path = None
                session.commit()
                return None
            job.status = JobStatus.RUNNING
            job.started_at = now
            job.updated_at = now
            context = JobContext(
                id=job.id,
                filename=job.filename,
                content_type=job.content_type,
                model=job.model,
                language=job.language,
                mode=job.mode,
                duration_s=job.duration_s,
                audio_path=Path(job.audio_path) if job.audio_path else None,
            )
            session.commit()
            return context

    def read_audio(self, context: JobContext) -> bytes:
        if context.audio_path is None or not context.audio_path.is_file():
            raise DomainError("Áudio do job não está mais disponível.", code="audio_missing")
        return context.audio_path.read_bytes()

    def finish_success(
        self,
        job_id: str,
        *,
        text: str,
        duration_s: float,
        transcribe_ms: int,
        raw_text: str | None = None,
        mode: str | None = None,
    ) -> Job:
        with self.session_factory() as session:
            job = self.jobs.get(session, job_id)
            if job is None:
                raise NotFoundError("Job não encontrado.")
            keep = self.settings.keep_audio
            row = new_transcription(
                text=text,
                raw_text=raw_text if raw_text is not None else text,
                mode=mode or job.mode,
                duration_s=duration_s,
                model=job.model,
                language=job.language,
                audio_path=job.audio_path if keep else None,
                audio_bytes=job.size_bytes,
                transcribe_ms=transcribe_ms,
                inserted=False,
            )
            self.transcriptions.add(session, row)
            job.transcription_id = row.id
            job.status = JobStatus.SUCCEEDED
            job.finished_at = local_stamp()
            job.updated_at = job.finished_at
            job.error = None
            if not keep:
                self.audio_store.delete(job.audio_path)
                job.audio_path = None
            session.commit()
            session.refresh(job)
            return job

    def finish_failure(self, job_id: str, *, error: str, duration_s: float) -> Job:
        with self.session_factory() as session:
            job = self.jobs.get(session, job_id)
            if job is None:
                raise NotFoundError("Job não encontrado.")
            if duration_s > 0:
                row = new_transcription(
                    text="",
                    duration_s=duration_s,
                    model=job.model,
                    language=job.language,
                    audio_path=job.audio_path if self.settings.keep_audio else None,
                    audio_bytes=job.size_bytes,
                    error=error,
                )
                self.transcriptions.add(session, row)
                job.transcription_id = row.id
            job.status = JobStatus.FAILED
            job.finished_at = local_stamp()
            job.updated_at = job.finished_at
            job.error = error
            if not self.settings.keep_audio:
                self.audio_store.delete(job.audio_path)
                job.audio_path = None
            session.commit()
            session.refresh(job)
            return job

    def mark_interrupted(
        self, job_id: str, *, reason: str = "Interrompido pelo encerramento da API."
    ) -> Job:
        with self.session_factory() as session:
            job = self.jobs.get(session, job_id)
            if job is None:
                raise NotFoundError("Job não encontrado.")
            if job.status in TERMINAL_STATUSES:
                session.expunge(job)
                return job
            now = local_stamp()
            job.status = JobStatus.FAILED
            job.finished_at = now
            job.updated_at = now
            job.error = reason
            session.commit()
            session.refresh(job)
            session.expunge(job)
            return job

    def mark_canceled(self, job_id: str, *, reason: str = "Cancelado pelo cliente.") -> Job:
        with self.session_factory() as session:
            job = self.jobs.get(session, job_id)
            if job is None:
                raise NotFoundError("Job não encontrado.")
            if job.status in TERMINAL_STATUSES:
                return job
            now = local_stamp()
            job.status = JobStatus.CANCELED
            job.finished_at = now
            job.updated_at = now
            job.error = job.error or reason
            self.audio_store.delete(job.audio_path)
            job.audio_path = None
            session.commit()
            session.refresh(job)
            return job

    def request_cancel(self, job_id: str) -> Job:
        with self.session_factory() as session:
            job = self.jobs.get(session, job_id)
            if job is None:
                raise NotFoundError("Job não encontrado.")
            if job.status in TERMINAL_STATUSES:
                session.expunge(job)
                return job
            job.cancel_requested = True
            job.updated_at = local_stamp()
            if job.status == JobStatus.QUEUED:
                job.status = JobStatus.CANCELED
                job.finished_at = job.updated_at
                self.audio_store.delete(job.audio_path)
                job.audio_path = None
            session.commit()
            session.refresh(job)
            session.expunge(job)
            return job

    # --- recuperação -------------------------------------------------------
    def recover_orphans(self) -> list[str]:
        """Fecha jobs interrompidos e devolve os enfileirados para reprocessar."""
        with self.session_factory() as session:
            interrupted = self.jobs.by_status(session, JobStatus.RUNNING)
            now = local_stamp()
            for job in interrupted:
                job.status = JobStatus.FAILED
                job.error = "Interrompido pelo encerramento da API."
                job.finished_at = now
                job.updated_at = now
            queued = [job.id for job in self.jobs.by_status(session, JobStatus.QUEUED)]
            session.commit()
            return queued
