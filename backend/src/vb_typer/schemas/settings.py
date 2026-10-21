"""Esquemas de configuração."""

from __future__ import annotations

from pydantic import BaseModel, Field

from vb_typer.schemas.common import ORMModel


class SettingsRead(ORMModel):
    model: str
    language: str
    mode: str
    default_profile: str
    smart_model: str
    allowed_smart_models: list[str]
    # Preço por modelo de texto: (entrada, saída) em US$ por 1M de tokens.
    text_prices: dict[str, list[float]] = Field(default_factory=dict)
    week_start: str
    api_key_configured: bool
    allowed_models: list[str]


class SettingsUpdate(BaseModel):
    model: str | None = None
    language: str | None = None
    mode: str | None = None
    default_profile: str | None = None
    smart_model: str | None = None
    week_start: str | None = None


class ConnectionTestResult(BaseModel):
    ok: bool
    models_available: int
    message: str
