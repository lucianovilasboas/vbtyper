"""Versões do ditado: aplica um perfil ao texto reconhecido.

Toda versão nasce de ``raw_text`` (a transcrição fiel), nunca de outra versão
editada — assim converter e-mail em ata não acumula erro de uma edição anterior.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from vb_typer.adapters.openai import OpenAIAdapter
from vb_typer.adapters.secrets import SecretsAdapter
from vb_typer.core.config import AppSettings
from vb_typer.core.timeutil import local_stamp
from vb_typer.db.models import Transcription, TranscriptionVersion
from vb_typer.domain.errors import DomainError, NotFoundError
from vb_typer.domain.pricing import text_cost_usd
from vb_typer.domain.profiles import compose_instructions, delivery_of, is_literal, tools_for
from vb_typer.domain.text_tools import apply_tools
from vb_typer.services.common import words_of
from vb_typer.services.history import HistoryService
from vb_typer.services.profiles import ProfileService
from vb_typer.services.settings import SettingsService


class RenditionService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: AppSettings,
        openai: OpenAIAdapter,
        secrets: SecretsAdapter,
        history: HistoryService,
        profiles: ProfileService,
        settings_service: SettingsService,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.openai = openai
        self.secrets = secrets
        self.history = history
        self.profiles = profiles
        self.settings_service = settings_service

    def versions(self, transcription_id: int) -> list[TranscriptionVersion]:
        with self.session_factory() as session:
            return list(
                session.scalars(
                    select(TranscriptionVersion)
                    .where(TranscriptionVersion.transcription_id == transcription_id)
                    .order_by(TranscriptionVersion.id)
                ).all()
            )

    async def render(self, transcription_id: int, profile_slug: str) -> Transcription:
        """Gera uma nova versão e a torna a atual. Falha não altera o texto."""
        row = self.history.get(transcription_id)
        profile = self.profiles.get(profile_slug)
        if is_literal(profile.slug):
            raise DomainError(
                "O perfil 'Transcrição fiel' é o próprio texto reconhecido: não há o que gerar.",
                code="invalid_profile",
            )
        source = (row.raw_text or row.text or "").strip()
        if not source:
            raise DomainError("Este ditado não tem texto para transformar.", code="empty_text")
        prepared = apply_tools(source, tools_for(profile, "before"), "before")
        if not prepared:
            raise DomainError("O texto ficou vazio após a preparação do perfil.", code="empty_text")

        # O modelo do perfil manda; sem ele, vale o padrão das configurações.
        model = profile.model or self.settings_service.smart_model_now()
        text, usage = await self.openai.normalize(
            text=prepared,
            model=model,
            instructions=compose_instructions(profile),
            api_key=self.secrets.get_api_key(),
        )
        after_tools = tools_for(profile, "after")
        final_text = apply_tools(text, after_tools, "after")
        if not final_text:
            raise DomainError("O texto ficou vazio após a limpeza do perfil.", code="empty_text")
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        cost = text_cost_usd(model, prompt_tokens, completion_tokens)

        with self.session_factory() as session:
            stored = session.get(Transcription, transcription_id)
            if stored is None:
                raise NotFoundError("Ditado não encontrado.")
            session.add(
                TranscriptionVersion(
                    transcription_id=transcription_id,
                    profile=profile.slug,
                    text=final_text,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=cost,
                    created_at=local_stamp(),
                )
            )
            stored.text = final_text
            stored.words = words_of(final_text)
            stored.profile = profile.slug
            stored.mode = "smart"
            stored.delivery = delivery_of(profile)
            stored.tools = after_tools
            session.commit()
            session.refresh(stored)
            return stored
