"""Memória curta entre ditados: o que já foi escrito vira contexto do próximo.

Só entra em ação quando o perfil pede (`options.continuo`) e quando há segunda
chamada — a transcrição fiel é o próprio reconhecido, sem ajuste.

O contexto é o **texto entregue** dos últimos ditados (o que está no documento),
dentro de uma janela curta e de um orçamento de caracteres. A janela conta a
partir de agora: quem dita de tempos em tempos mantém o fio; quem volta no dia
seguinte começa limpo. Nenhuma falha aqui pode derrubar o ditado.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from vb_typer.db.models import Transcription
from vb_typer.domain.profiles import (
    CONTINUITY_MAX_CHARS,
    CONTINUITY_MAX_ITEMS,
    CONTINUITY_MIN_CHUNK,
    CONTINUITY_WINDOW_MINUTES,
    ProfileSpec,
    is_literal,
)


@dataclass(frozen=True)
class ContinuityContext:
    """O que será mandado como contexto, e de quantos ditados ele veio."""

    text: str = ""
    count: int = 0

    @property
    def enabled(self) -> bool:
        return bool(self.text)


def join_context(
    texts: list[str], max_chars: int, min_chunk: int = CONTINUITY_MIN_CHUNK
) -> ContinuityContext:
    """Junta os ditados (do mais antigo ao mais novo) dentro do orçamento.

    O corte é sempre no começo do ditado mais antigo: o que interessa é a cauda
    recente do que foi escrito, não o histórico inteiro. A contagem diz de
    quantos ditados o contexto realmente veio.
    """
    kept: list[str] = []
    used = 0
    for text in reversed([item.strip() for item in texts if item.strip()]):
        remaining = max_chars - used
        if remaining <= 0:
            break
        if len(text) <= remaining:
            kept.append(text)
            used += len(text) + 2  # o separador entra na conta
            continue
        if remaining >= min_chunk:
            kept.append("…" + text[-remaining:].lstrip())
        break
    joined = "\n\n".join(reversed(kept))
    return ContinuityContext(text=joined, count=len(kept))


class ContinuityService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        window_minutes: int = CONTINUITY_WINDOW_MINUTES,
        max_items: int = CONTINUITY_MAX_ITEMS,
        max_chars: int = CONTINUITY_MAX_CHARS,
    ) -> None:
        self.session_factory = session_factory
        self.window_minutes = window_minutes
        self.max_items = max_items
        self.max_chars = max_chars

    @staticmethod
    def accepts(profile: ProfileSpec | None) -> bool:
        """O perfil pede continuidade? A transcrição fiel nunca tem segunda chamada."""
        if profile is None or is_literal(profile.slug):
            return False
        return bool((profile.options or {}).get("continuo"))

    def context_for(
        self, *, exclude_id: int | None = None, now: datetime | None = None
    ) -> ContinuityContext:
        """Ditados recentes como contexto; vazio quando não há o que aproveitar."""
        reference = now or datetime.now()
        since = (reference - timedelta(minutes=self.window_minutes)).strftime("%Y-%m-%d %H:%M:%S")
        stmt = select(Transcription).where(
            Transcription.created_at >= since,
            Transcription.error.is_(None),
            Transcription.text != "",
        )
        if exclude_id is not None:
            stmt = stmt.where(Transcription.id != exclude_id)
        try:
            with self.session_factory() as session:
                rows = list(
                    session.scalars(
                        stmt.order_by(Transcription.id.desc()).limit(self.max_items)
                    ).all()
                )
        except Exception:  # pragma: no cover - banco indisponível não derruba o ditado
            return ContinuityContext()
        texts = [row.text for row in reversed(rows)]
        return join_context(texts, self.max_chars)
