"""Configurações do backend (nunca expõem a chave)."""

from __future__ import annotations

import asyncio
import hashlib
import json

from fastapi import APIRouter, status

from vb_typer.api.deps import ContainerDep
from vb_typer.domain.hotkeys import DEFAULT_HOTKEYS
from vb_typer.domain.pricing import DEFAULT_TEXT_PRICING, TEXT_PRICING_PER_MILLION
from vb_typer.schemas.settings import ConnectionTestResult, SettingsRead, SettingsUpdate

router = APIRouter(prefix="/settings", tags=["configuração"])


def _text_prices(models: tuple[str, ...] | list[str]) -> dict[str, list[float]]:
    """Preço (entrada, saída) por 1M de tokens — a tabela do domínio é a fonte."""
    return {name: list(TEXT_PRICING_PER_MILLION.get(name, DEFAULT_TEXT_PRICING)) for name in models}


def _version(values: dict) -> str:
    """Impressão digital das escolhas editáveis (12 caracteres).

    Os clientes consultam ``/settings`` de tempos em tempos; comparar isto diz se
    algo mudou (inclusive de outro aparelho) sem depender do relógio: duas
    edições no mesmo segundo geram versões diferentes.
    """
    body = json.dumps(values, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(body.encode("utf-8")).hexdigest()[:12]


def _read(container: ContainerDep) -> SettingsRead:
    row = container.settings_service.current()
    hotkeys = dict(row.hotkeys or DEFAULT_HOTKEYS)
    sample = SettingsRead(
        model=row.model,
        language=row.language,
        mode=row.mode,
        default_profile=row.default_profile,
        smart_model=row.smart_model,
        allowed_smart_models=list(container.settings.allowed_smart_models),
        text_prices=_text_prices(container.settings.allowed_smart_models),
        week_start=row.week_start,
        hotkeys=hotkeys,
        default_hotkeys=dict(DEFAULT_HOTKEYS),
        api_key_configured=container.transcription.api_key_present(),
        allowed_models=list(container.settings.allowed_models),
        version=_version(
            {
                "model": row.model,
                "language": row.language,
                "mode": row.mode,
                "default_profile": row.default_profile,
                "smart_model": row.smart_model,
                "week_start": row.week_start,
                "hotkeys": hotkeys,
                # A lista de perfis também é escolha do usuário: renomear ou
                # criar um perfil precisa chegar à bandeja sem polling extra.
                "profiles": container.profiles.signature(),
            }
        ),
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
