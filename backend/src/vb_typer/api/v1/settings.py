"""Configurações do backend (nunca expõem a chave)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, status

from vb_typer.api.deps import ContainerDep
from vb_typer.domain.hotkeys import DEFAULT_HOTKEYS
from vb_typer.domain.pricing import DEFAULT_TEXT_PRICING, TEXT_PRICING_PER_MILLION
from vb_typer.schemas.settings import ConnectionTestResult, SettingsRead, SettingsUpdate

router = APIRouter(prefix="/settings", tags=["configuração"])


def _text_prices(models: tuple[str, ...] | list[str]) -> dict[str, list[float]]:
    """Preço (entrada, saída) por 1M de tokens — a tabela do domínio é a fonte."""
    return {name: list(TEXT_PRICING_PER_MILLION.get(name, DEFAULT_TEXT_PRICING)) for name in models}


def _read(container: ContainerDep) -> SettingsRead:
    row = container.settings_service.current()
    sample = SettingsRead(
        model=row.model,
        language=row.language,
        mode=row.mode,
        default_profile=row.default_profile,
        smart_model=row.smart_model,
        allowed_smart_models=list(container.settings.allowed_smart_models),
        text_prices=_text_prices(container.settings.allowed_smart_models),
        week_start=row.week_start,
        hotkeys=dict(row.hotkeys or DEFAULT_HOTKEYS),
        default_hotkeys=dict(DEFAULT_HOTKEYS),
        api_key_configured=container.transcription.api_key_present(),
        allowed_models=list(container.settings.allowed_models),
    )
    return sample


@router.get("", response_model=SettingsRead)
def read_settings(container: ContainerDep) -> SettingsRead:
    return _read(container)


@router.patch("", response_model=SettingsRead)
def update_settings(payload: SettingsUpdate, container: ContainerDep) -> SettingsRead:
    container.settings_service.update(
        model=payload.model,
        language=payload.language,
        mode=payload.mode,
        default_profile=payload.default_profile,
        smart_model=payload.smart_model,
        week_start=payload.week_start,
        hotkeys=payload.hotkeys,
    )
    return _read(container)


@router.post("/test", response_model=ConnectionTestResult, status_code=status.HTTP_200_OK)
async def test_connection(container: ContainerDep) -> ConnectionTestResult:
    """GET somente leitura em ``/models``; não transcreve áudio."""
    api_key = await asyncio.to_thread(container.secrets.get_api_key)
    count = await container.openai.check(api_key)
    return ConnectionTestResult(
        ok=True,
        models_available=count,
        message="Conexão com a OpenAI verificada.",
    )
