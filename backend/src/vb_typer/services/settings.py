"""Configurações editáveis (modelo, idioma, início da semana)."""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from vb_typer.core.config import TRANSCRIPTION_MODES, WEEK_STARTS, AppSettings
from vb_typer.core.timeutil import local_stamp
from vb_typer.db.models import AppSetting
from vb_typer.domain.errors import DomainError, InvalidModelError


class SettingsService:
    def __init__(self, session_factory: sessionmaker[Session], settings: AppSettings) -> None:
        self.session_factory = session_factory
        self.settings = settings

    def current(self) -> AppSetting:
        with self.session_factory() as session:
            row = session.get(AppSetting, 1)
            if row is None:
                row = AppSetting(
                    id=1,
                    model=self.settings.default_model,
                    language=self.settings.default_language,
                    mode=self.settings.default_mode,
                    week_start=self.settings.week_start,
                    updated_at=local_stamp(),
                )
                session.add(row)
                session.commit()
            session.refresh(row)
            return row

    def update(
        self,
        *,
        model: str | None = None,
        language: str | None = None,
        mode: str | None = None,
        week_start: str | None = None,
    ) -> AppSetting:
        with self.session_factory() as session:
            row = session.get(AppSetting, 1)
            if row is None:
                row = AppSetting(
                    id=1,
                    model=self.settings.default_model,
                    language=self.settings.default_language,
                    mode=self.settings.default_mode,
                    week_start=self.settings.week_start,
                    updated_at=local_stamp(),
                )
                session.add(row)
            if model is not None:
                if model not in self.settings.allowed_models:
                    raise InvalidModelError(
                        f"Modelo inválido. Use um de: {', '.join(self.settings.allowed_models)}."
                    )
                row.model = model
            if language is not None:
                normalized = language.strip().lower()
                if not 2 <= len(normalized) <= 16:
                    raise DomainError("Idioma inválido.", code="invalid_language")
                row.language = normalized
            if mode is not None:
                normalized = mode.strip().lower()
                if normalized not in TRANSCRIPTION_MODES:
                    raise DomainError(
                        f"Modo inválido. Use um de: {TRANSCRIPTION_MODES}.", code="invalid_mode"
                    )
                row.mode = normalized
            if week_start is not None:
                normalized = week_start.strip().lower()
                if normalized not in WEEK_STARTS:
                    raise DomainError(
                        f"week_start deve ser um de {WEEK_STARTS}.", code="invalid_week_start"
                    )
                row.week_start = normalized
            row.updated_at = local_stamp()
            session.commit()
            session.refresh(row)
            return row
