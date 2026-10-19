"""Enums e constantes do domínio."""

from __future__ import annotations

from enum import StrEnum

from vb_typer.core.config import DEFAULT_ALLOWED_MODELS

ALLOWED_MODELS: tuple[str, ...] = tuple(DEFAULT_ALLOWED_MODELS)


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class TranscriptionMode(StrEnum):
    """Como o texto ditado é entregue.

    ``LITERAL`` preserva exatamente as palavras reconhecidas (padrão);
    ``SMART`` passa o texto por um ajuste que converte datas, números, valores e
    siglas para formatos convencionais.
    """

    LITERAL = "literal"
    SMART = "smart"


TERMINAL_STATUSES = frozenset({JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELED})


class Granularity(StrEnum):
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


# Tarifas públicas da OpenAI por minuto de áudio (US$).
PRICING_PER_MINUTE = {
    "gpt-4o-mini-transcribe": 0.003,
    "gpt-transcribe": 0.0045,
    "gpt-4o-transcribe": 0.006,
    "whisper-1": 0.006,
}
DEFAULT_PRICE_PER_MINUTE = 0.0045
