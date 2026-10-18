"""Configuração da aplicação, carregada de variáveis de ambiente e `.env`."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Modelos aceitos pelo domínio. A lista de preços fica em `vb_typer.services.stats`.
DEFAULT_ALLOWED_MODELS = ("gpt-4o-mini-transcribe", "gpt-transcribe")
DEFAULT_ALLOWED_CONTENT_TYPES = (
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/webm",
    "audio/ogg",
    "audio/mpeg",
    "audio/mp4",
    "audio/x-m4a",
    "audio/m4a",
)

WEEK_STARTS = ("monday", "sunday")


def _split_csv(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ()
        if stripped.startswith("["):
            return value
        return tuple(part.strip() for part in stripped.split(",") if part.strip())
    return value


class AppSettings(BaseSettings):
    """Configuração efetiva do processo.

    Todas as variáveis usam o prefixo ``VB_TYPER_`` (ex.: ``VB_TYPER_PORT``).
    Nada sensível é lido daqui: a chave OpenAI vive no cofre do sistema.
    """

    model_config = SettingsConfigDict(
        env_prefix="VB_TYPER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "VB Typer API"
    host: str = "127.0.0.1"
    port: int = 8765
    log_level: str = "INFO"

    # Diretórios explícitos (usados em testes). Quando vazios, `platformdirs` decide.
    config_dir: Path | None = None
    data_dir: Path | None = None
    database_path: Path | None = None

    # Segurança local.
    api_token: str | None = None
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost")
    cors_origins: tuple[str, ...] = ()
    trust_origin_header: bool = True

    # OpenAI.
    openai_base_url: str = "https://api.openai.com/v1"
    openai_timeout_s: float = 120.0
    keyring_service: str = "VibeTyper"
    keyring_username: str = "openai_api_key"

    # Áudio e transcrição.
    max_upload_bytes: int = 25 * 1024 * 1024
    max_audio_seconds: float = 120.0
    allowed_models: tuple[str, ...] = DEFAULT_ALLOWED_MODELS
    allowed_content_types: tuple[str, ...] = DEFAULT_ALLOWED_CONTENT_TYPES
    default_model: str = "gpt-4o-mini-transcribe"
    default_language: str = "pt"
    keep_audio: bool = True
    week_start: str = "monday"

    # Worker de jobs.
    worker_concurrency: int = Field(default=2, ge=1, le=16)

    @field_validator(
        "allowed_hosts",
        "cors_origins",
        "allowed_models",
        "allowed_content_types",
        mode="before",
    )
    @classmethod
    def _parse_lists(cls, value: Any) -> Any:
        return _split_csv(value)

    @field_validator("week_start")
    @classmethod
    def _parse_week_start(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in WEEK_STARTS:
            raise ValueError(f"week_start deve ser um de {WEEK_STARTS}")
        return normalized

    @field_validator("log_level")
    @classmethod
    def _parse_level(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("openai_base_url")
    @classmethod
    def _parse_base_url(cls, value: str) -> str:
        return value.rstrip("/")


@lru_cache
def get_settings() -> AppSettings:
    """Configuração em cache para uso fora do ciclo da aplicação (CLI)."""
    return AppSettings()
