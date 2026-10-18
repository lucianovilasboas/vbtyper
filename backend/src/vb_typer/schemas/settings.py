"""Esquemas de configuração."""

from __future__ import annotations

from pydantic import BaseModel

from vb_typer.schemas.common import ORMModel


class SettingsRead(ORMModel):
    model: str
    language: str
    week_start: str
    api_key_configured: bool
    allowed_models: list[str]


class SettingsUpdate(BaseModel):
    model: str | None = None
    language: str | None = None
    week_start: str | None = None


class ConnectionTestResult(BaseModel):
    ok: bool
    models_available: int
    message: str
