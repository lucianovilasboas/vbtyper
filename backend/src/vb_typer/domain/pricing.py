"""Preços em dólar: áudio transcrito e texto processado pelos perfis.

As tabelas ficam em `domain/enums.py` (áudio) e aqui (texto). Estas funções são
a única fórmula: o histórico, as estatísticas, as versões e o CSV usam a mesma.
"""

from __future__ import annotations

from vb_typer.domain.enums import DEFAULT_PRICE_PER_MINUTE, PRICING_PER_MINUTE

# Tarifas públicas da OpenAI por 1 milhão de tokens (entrada, saída).
TEXT_PRICING_PER_MILLION: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
}

DEFAULT_TEXT_PRICING = (0.15, 0.60)


def cost_usd(model: str, duration_s: float) -> float:
    """Custo estimado de ``duration_s`` segundos transcritos com ``model``."""
    rate = PRICING_PER_MINUTE.get(model or "", DEFAULT_PRICE_PER_MINUTE)
    return max(0.0, float(duration_s or 0.0)) / 60.0 * rate


def text_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Custo estimado de uma chamada de texto, a partir do ``usage``."""
    input_rate, output_rate = TEXT_PRICING_PER_MILLION.get(model or "", DEFAULT_TEXT_PRICING)
    total = (
        int(prompt_tokens or 0) * input_rate + int(completion_tokens or 0) * output_rate
    ) / 1_000_000
    return round(max(0.0, total), 6)
