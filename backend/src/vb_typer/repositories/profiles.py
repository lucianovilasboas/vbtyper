"""Acesso aos perfis personalizados."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from vb_typer.db.models import Profile


class ProfileRepository:
    def list(self, session: Session) -> list[Profile]:
        return list(
            session.scalars(
                select(Profile).order_by(Profile.seeded.desc(), Profile.sort_order, Profile.name)
            ).all()
        )

    def get(self, session: Session, slug: str) -> Profile | None:
        return session.scalar(select(Profile).where(Profile.slug == slug))

    def signature(self, session: Session) -> list[tuple[str, str, str]]:
        """Slug, nome e instante de edição de cada perfil — a "impressão digital".

        Alimenta a versão das configurações: renomear, criar ou apagar um perfil
        muda a versão, e os clientes voltam a buscar a lista sem polling extra.
        """
        rows = session.execute(
            select(Profile.slug, Profile.name, Profile.updated_at).order_by(
                Profile.seeded.desc(), Profile.sort_order, Profile.name
            )
        ).all()
        return [(str(slug), str(name), str(updated)) for slug, name, updated in rows]

    def add(self, session: Session, row: Profile) -> None:
        session.add(row)

    def delete(self, session: Session, row: Profile) -> None:
        session.delete(row)
