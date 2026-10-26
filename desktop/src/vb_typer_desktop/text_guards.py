"""Guardas de entrega do cliente, aplicadas imediatamente antes de digitar.

O backend já entrega o texto limpo; esta é a última milha. O registro é por
destino (``text``, ``tui``, ...): um destino novo no backend não quebra um
cliente antigo — sem guard conhecido, o texto passa intacto.
"""

from __future__ import annotations

import re
from collections.abc import Callable

# Mesma ordem do preset TUI do backend: ANSI, tabs, quebras, espaços, controles.
LINE_BREAK_RE = re.compile(r"[\r\n\v\f\x85\u2028\u2029]+")
SPACES_RE = re.compile(r"[ \t]+")
ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\)|[@-Z\\-_])")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def tui_guard(text: str) -> str:
    """Uma linha, sem ESC/controles e sem Tab (que disparam Enter/Tab no TUI)."""
    value = ANSI_RE.sub("", text or "")
    value = value.replace("\t", " ")
    value = LINE_BREAK_RE.sub(" ", value)
    value = SPACES_RE.sub(" ", value)
    value = CONTROL_RE.sub("", value)
    return value.strip()


GUARDS: dict[str, Callable[[str], str]] = {"tui": tui_guard}


def apply_guard(text: str, delivery: str) -> str:
    """Aplica o guard do destino; destino desconhecido devolve o texto como veio."""
    guard = GUARDS.get((delivery or "text").strip().lower())
    return guard(text) if guard is not None else text
