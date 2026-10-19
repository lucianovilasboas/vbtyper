"""Preço do áudio transcrito, em dólar.

A tabela fica em `domain/enums.py` (tarifas públicas da OpenAI). Esta função é
a única fórmula: o histórico, as estatísticas e o CSV usam a mesma.
"""

from __future__ import annotations

from vb_typer.domain.enums import DEFAULT_PRICE_PER_MINUTE, PRICING_PER_MINUTE


def cost_usd(model: str, duration_s: float) -> float:
    """Custo estimado de ``duration_s`` segundos transcritos com ``model``."""
    rate = PRICING_PER_MINUTE.get(model or "", DEFAULT_PRICE_PER_MINUTE)
    return max(0.0, float(duration_s or 0.0)) / 60.0 * rate
