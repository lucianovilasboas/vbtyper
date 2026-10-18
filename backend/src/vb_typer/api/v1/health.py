"""Rotas públicas de saúde/prontidão (sem autenticação e sem segredos)."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from sqlalchemy import text

from vb_typer.api.deps import ContainerDep

logger = logging.getLogger(__name__)

router = APIRouter(tags=["saúde"])


@router.get("/health")
def health(container: ContainerDep) -> dict:
    return {
        "status": "ok",
        "app": container.settings.app_name,
        "version": container.version,
    }


@router.get("/ready")
def ready(container: ContainerDep) -> dict:
    database_ok = True
    try:
        with container.session_factory() as session:
            session.execute(text("SELECT 1"))
    except Exception:
        database_ok = False
        logger.warning("Banco indisponível na checagem de prontidão.", exc_info=True)
    return {
        "status": "ok" if database_ok else "degraded",
        "database": database_ok,
        "api_key_configured": container.transcription.api_key_present(),
        "models": list(container.settings.allowed_models),
    }
