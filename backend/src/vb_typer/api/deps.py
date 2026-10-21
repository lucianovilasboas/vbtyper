"""Dependências do FastAPI e composição dos serviços."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from vb_typer import __version__
from vb_typer.adapters.audio_store import AudioStore
from vb_typer.adapters.openai import OpenAIAdapter
from vb_typer.adapters.secrets import SecretsAdapter
from vb_typer.core.config import AppSettings
from vb_typer.core.paths import AppPaths
from vb_typer.core.security import TOKEN_COOKIE, bearer_token, token_matches
from vb_typer.db.session import make_engine, make_session_factory
from vb_typer.domain.errors import UnauthorizedError
from vb_typer.services.history import HistoryService
from vb_typer.services.profiles import ProfileService
from vb_typer.services.renditions import RenditionService
from vb_typer.services.settings import SettingsService
from vb_typer.services.stats import StatsService
from vb_typer.services.transcription import TranscriptionService
from vb_typer.workers.manager import JobManager


@dataclass
class Container:
    settings: AppSettings
    paths: AppPaths
    engine: Engine
    session_factory: sessionmaker[Session]
    secrets: SecretsAdapter
    audio_store: AudioStore
    openai: OpenAIAdapter
    history: HistoryService
    stats: StatsService
    settings_service: SettingsService
    profiles: ProfileService
    renditions: RenditionService
    transcription: TranscriptionService

    @property
    def version(self) -> str:
        return __version__


def build_container(settings: AppSettings, paths: AppPaths) -> Container:
    engine = make_engine(paths.database)
    session_factory = make_session_factory(engine)
    secrets = SecretsAdapter(settings)
    audio_store = AudioStore(
        paths.audio_dir, settings.max_upload_bytes, settings.allowed_content_types
    )
    openai = OpenAIAdapter(settings.openai_base_url, settings.openai_timeout_s)
    profiles = ProfileService(session_factory)
    history = HistoryService(session_factory, settings, audio_store)
    return Container(
        settings=settings,
        paths=paths,
        engine=engine,
        session_factory=session_factory,
        secrets=secrets,
        audio_store=audio_store,
        openai=openai,
        history=history,
        stats=StatsService(session_factory, settings),
        settings_service=SettingsService(session_factory, settings),
        profiles=profiles,
        renditions=RenditionService(session_factory, settings, openai, secrets, history, profiles),
        transcription=TranscriptionService(
            session_factory, settings, audio_store, secrets, profiles
        ),
    )


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_app_settings(request: Request) -> AppSettings:
    return request.app.state.container.settings


def get_manager(request: Request) -> JobManager:
    return request.app.state.manager


async def require_token(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Aceita ``Authorization: Bearer`` ou o cookie de mesma origem do app web."""
    expected = request.app.state.api_token
    provided = bearer_token(authorization) or request.cookies.get(TOKEN_COOKIE)
    if not token_matches(provided, expected):
        raise UnauthorizedError("Token de acesso ausente ou inválido.")


ContainerDep = Annotated[Container, Depends(get_container)]
ManagerDep = Annotated[JobManager, Depends(get_manager)]
