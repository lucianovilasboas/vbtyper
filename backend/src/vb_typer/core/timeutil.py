"""Utilitários de data/hora.

O banco guarda horários locais no formato ``YYYY-MM-DD HH:MM:SS`` para que as
estatísticas por hora/dia reflitam o fuso do usuário sem conversões frágeis.
"""

from __future__ import annotations

from datetime import datetime


def local_stamp(moment: datetime | None = None) -> str:
    return (moment or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")


def parse_local_stamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def iso_stamp(value: str) -> str:
    """Converte o formato do banco para ISO-8601 mantendo o horário local."""
    return value.replace(" ", "T", 1)


def normalize_bound(value: str | None, *, upper: bool = False) -> str | None:
    """Aceita ``YYYY-MM-DD``, ISO-8601 ou ``YYYY-MM-DD HH:MM:SS``.

    Um limite superior só com data representa o fim do dia.
    """
    if not value:
        return None
    text = value.strip().replace("T", " ")
    if len(text) == 10:
        return f"{text} {'23:59:59' if upper else '00:00:00'}"
    if len(text) == 16:
        return f"{text}:{'59' if upper else '00'}"
    return text[:19]
