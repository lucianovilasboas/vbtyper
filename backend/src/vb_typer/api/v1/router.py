"""Roteador da versão 1 da API."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from vb_typer.api.deps import require_token
from vb_typer.api.v1 import health, jobs, settings, stats, transcriptions

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)

protected = APIRouter(dependencies=[Depends(require_token)])
protected.include_router(settings.router)
protected.include_router(jobs.router)
protected.include_router(transcriptions.router)
protected.include_router(stats.router)

api_router.include_router(protected)
