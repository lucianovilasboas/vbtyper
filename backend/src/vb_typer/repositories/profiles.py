"""Acesso aos perfis personalizados."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from vb_typer.db.models import Profile


class ProfileRepository:
    def list(self, session: Session) -> list[Profile]:
        return list(session.scalars(select(Profile).order_by(Profile.name)).all())

    def get(self, session: Session, slug: str) -> Profile | None:
        return session.scalar(select(Profile).where(Profile.slug == slug))

    def add(self, session: Session, row: Profile) -> None:
        session.add(row)

    def delete(self, session: Session, row: Profile) -> None:
        session.delete(row)
