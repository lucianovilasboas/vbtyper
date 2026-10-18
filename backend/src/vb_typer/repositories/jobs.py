"""Repositório de jobs de transcrição."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from vb_typer.db.models import Job


class JobRepository:
    def get(self, session: Session, job_id: str) -> Job | None:
        return session.get(Job, job_id)

    def add(self, session: Session, job: Job) -> Job:
        session.add(job)
        session.flush()
        return job

    def list(self, session: Session, limit: int = 20, status: str | None = None) -> list[Job]:
        stmt = select(Job).order_by(Job.created_at.desc(), Job.id.desc()).limit(limit)
        if status:
            stmt = stmt.where(Job.status == status)
        return list(session.scalars(stmt).all())

    def by_status(self, session: Session, *statuses: str) -> list[Job]:
        stmt = select(Job).where(Job.status.in_(statuses)).order_by(Job.created_at.asc())
        return list(session.scalars(stmt).all())
