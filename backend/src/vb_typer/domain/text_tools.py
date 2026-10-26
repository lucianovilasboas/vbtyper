"""Transformações determinísticas de texto do pipeline de perfis.

O perfil declara um **destino** (``delivery``) e **ferramentas extras**
(``options.tools``/``tools_before``). O destino é um preset semântico
(``text``, ``tui``, ...) que define a limpeza final e um hint para a LLM; as
ferramentas extras rodam antes do preset. TUI é um destino, não a regra.

As funções são puras, idempotentes e não conhecem banco, HTTP ou LLM.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

# Linhas que viram espaço: CRLF, CR, LF, tabulação vertical, form feed, NEL e
# os separadores Unicode de linha/parágrafo (que também quebram linha em TUI).
LINE_BREAK_RE = re.compile(r"[\r\n\v\f\x85\u2028\u2029]+")
SPACES_RE = re.compile(r"[ \t]+")
# ESC seguido de CSI, OSC ou uma sequência de dois caracteres.
ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\)|[@-Z\\-_])")
# C0/C1 e DEL, preservando \t, \n e \r (whitespace tratado por single_line).
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
FENCE_RE = re.compile(r"^[ \t]*(?:```|~~~)[^\n]*$", re.MULTILINE)
HEADING_RE = re.compile(r"^[ \t]*#{1,6}[ \t]+", re.MULTILINE)
LIST_RE = re.compile(r"^[ \t]*[-*+][ \t]+", re.MULTILINE)
QUOTE_RE = re.compile(r"^[ \t]*>[ \t]?", re.MULTILINE)
BOLD_RE = re.compile(r"(\*\*|__)(.+?)\1", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")

Phase = str
ToolFn = Callable[[str], str]


@dataclass(frozen=True)
class TextTool:
    name: str
    description: str
    phases: frozenset[str]
    apply: ToolFn


def strip_ansi(text: str) -> str:
    """Remove sequências ANSI/ESC (cores, títulos, hyperlinks de terminal)."""
    return ANSI_RE.sub("", text)


def strip_control(text: str) -> str:
    """Remove controles C0/C1 e DEL; preserva tab, LF e CR."""
    return CONTROL_RE.sub("", text)


def spaces_for_tabs(text: str) -> str:
    """Tab não deve disparar completação/indentação em um terminal."""
    return text.replace("\t", " ")


def single_line(text: str) -> str:
    """Deixa o texto em uma linha, com espaços simples e sem pontas."""
    value = LINE_BREAK_RE.sub(" ", text)
    return SPACES_RE.sub(" ", value).strip()


def trim(text: str) -> str:
    return text.strip()


def strip_markdown(text: str) -> str:
    """Remove cercas, títulos, listas, citações, negrito e código inline.

    Conservador de propósito: não reescreve links nem o conteúdo do texto.
    """
    value = FENCE_RE.sub("", text)
    value = HEADING_RE.sub("", value)
    value = LIST_RE.sub("", value)
    value = QUOTE_RE.sub("", value)
    value = BOLD_RE.sub(r"\2", value)
    value = INLINE_CODE_RE.sub(r"\1", value)
    return value


TOOLS: dict[str, TextTool] = {
    "strip_ansi": TextTool(
        "strip_ansi",
        "remove sequências ANSI/ESC",
        frozenset({"before", "after"}),
        strip_ansi,
    ),
    "strip_control": TextTool(
        "strip_control",
        "remove caracteres de controle (C0/C1/DEL)",
        frozenset({"before", "after"}),
        strip_control,
    ),
    "spaces_for_tabs": TextTool(
        "spaces_for_tabs",
        "troca tabulações por espaços",
        frozenset({"after"}),
        spaces_for_tabs,
    ),
    "single_line": TextTool(
        "single_line",
        "transforma quebras de linha em espaços e deixa uma linha só",
        frozenset({"after"}),
        single_line,
    ),
    "trim": TextTool("trim", "remove espaços do começo e do fim", frozenset({"after"}), trim),
    "strip_markdown": TextTool(
        "strip_markdown",
        "remove marcadores de Markdown",
        frozenset({"after"}),
        strip_markdown,
    ),
}

# Presets por destino. O destino é aplicado **depois** das ferramentas extras,
# para ser a limpeza final (ex.: strip_markdown antes de single_line).
TARGETS: dict[str, tuple[str, ...]] = {
    "text": (),
    "tui": ("strip_ansi", "spaces_for_tabs", "single_line", "strip_control", "trim"),
}

TARGET_HINTS: dict[str, str] = {
    "tui": "Entregue o texto em uma única linha, sem quebras de linha nem tabulações.",
}

TARGET_LABELS: dict[str, str] = {
    "text": "Texto normal",
    "tui": "Terminal (TUI)",
}

PHASES = ("before", "after")


def _name(value: object) -> str:
    return str(value or "").strip().lower()


def known_targets() -> tuple[str, ...]:
    return tuple(TARGETS)


def known_tools() -> tuple[str, ...]:
    return tuple(TOOLS)


def validate_tools(names: object, phase: str) -> list[str]:
    """Normaliza e valida uma lista de ferramentas para a fase indicada."""
    if phase not in PHASES:
        raise ValueError(f"Fase inválida: {phase}.")
    if names is None:
        return []
    if not isinstance(names, (list, tuple)):
        raise ValueError("A lista de ferramentas deve ser uma lista de nomes.")
    result: list[str] = []
    for raw in names:
        name = _name(raw)
        if not name:
            continue
        tool = TOOLS.get(name)
        if tool is None:
            raise ValueError(f"Ferramenta de texto desconhecida: {name}.")
        if phase not in tool.phases:
            raise ValueError(f"A ferramenta {name} não pode ser usada em {phase}.")
        if name not in result:
            result.append(name)
    return result


def effective_tools(delivery: str, extras: object = (), phase: str = "after") -> list[str]:
    """Ferramentas efetivas: extras (ordem do usuário) + preset do destino."""
    target = _name(delivery) or "text"
    if target not in TARGETS:
        raise ValueError(f"Destino de texto desconhecido: {target}.")
    extra_names = validate_tools(extras, phase)
    if phase == "before":
        return extra_names
    return validate_tools([*extra_names, *TARGETS[target]], "after")


def apply_tools(text: str, names: object, phase: str = "after") -> str:
    """Aplica as ferramentas na ordem informada; entrada vazia continua vazia."""
    value = text or ""
    for name in validate_tools(names, phase):
        value = TOOLS[name].apply(value)
    return value


def target_hint(delivery: str) -> str:
    return TARGET_HINTS.get(_name(delivery) or "text", "")
