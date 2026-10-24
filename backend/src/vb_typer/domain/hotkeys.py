"""Atalhos globais do cliente desktop: uma gramática só, validada aqui.

A interface web captura a combinação (pelo ``code`` físico da tecla, para não
depender do layout) e manda no formato ``ctrl+alt+Tab``. O cliente desktop lê a
mesma string e a traduz para os keycodes do sistema. Validar no backend evita
que uma combinação impossível chegue ao grab do X.

Ctrl+Super juntos ficam de fora: é o atalho de gravar (segurar os dois), e um
combo de perfil começaria um ditado em vez de trocar o perfil.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from vb_typer.domain.errors import DomainError

MODIFIERS = ("ctrl", "alt", "shift", "super")

# Nomes canônicos das teclas: os mesmos que o ``KeyboardEvent.code`` do
# navegador entrega (sem os prefixos Key/Digit) e que o cliente desktop sabe
# converter em keysym.
KEY_NAMES = frozenset(
    [*"ABCDEFGHIJKLMNOPQRSTUVWXYZ", *"0123456789"]
    + [f"F{number}" for number in range(1, 13)]
    + [
        "Tab",
        "Space",
        "Enter",
        "Backspace",
        "Delete",
        "Insert",
        "Home",
        "End",
        "PageUp",
        "PageDown",
        "ArrowUp",
        "ArrowDown",
        "ArrowLeft",
        "ArrowRight",
        "Backquote",
        "Minus",
        "Equal",
        "BracketLeft",
        "BracketRight",
        "Backslash",
        "Semicolon",
        "Quote",
        "Comma",
        "Period",
        "Slash",
    ]
)
_BY_NAME = {name.casefold(): name for name in KEY_NAMES}

PROFILE_NEXT = "profile_next"
PROFILE_PREVIOUS = "profile_previous"
PROFILE_DEFAULT = "profile_default"
HOTKEY_ACTIONS = (PROFILE_NEXT, PROFILE_PREVIOUS, PROFILE_DEFAULT)

DEFAULT_HOTKEYS: dict[str, str] = {
    PROFILE_NEXT: "ctrl+alt+Tab",
    PROFILE_PREVIOUS: "ctrl+alt+shift+Tab",
    PROFILE_DEFAULT: "ctrl+alt+0",
}


def _invalid(message: str) -> DomainError:
    return DomainError(message, code="invalid_hotkey")


def parse(text: str) -> tuple[tuple[str, ...], str]:
    """Separa modificadores e tecla; devolve na ordem canônica dos modificadores."""
    raw = (text or "").strip()
    if not raw:
        raise _invalid("Informe a combinação, como ctrl+alt+Tab.")
    parts = [part.strip() for part in raw.split("+")]
    if len(parts) < 2 or any(not part for part in parts):
        raise _invalid("Combinação inválida: use modificadores e uma tecla, como ctrl+alt+Tab.")
    *raw_modifiers, raw_key = parts

    modifiers = [part.casefold() for part in raw_modifiers]
    for name in modifiers:
        if name not in MODIFIERS:
            raise _invalid(f"Modificador desconhecido: {name}. Use ctrl, alt, shift ou super.")
    if len(set(modifiers)) != len(modifiers):
        raise _invalid("Modificador repetido na combinação.")
    if "ctrl" in modifiers and "super" in modifiers:
        raise _invalid("Ctrl+Super é o atalho de gravar. Escolha outra combinação.")

    key = _BY_NAME.get(raw_key.casefold())
    if key is None:
        raise _invalid(f"Tecla desconhecida: {raw_key}.")
    return tuple(name for name in MODIFIERS if name in modifiers), key


def render(modifiers: Iterable[str], key: str) -> str:
    return "+".join([*modifiers, key])


def normalize(text: str) -> str:
    """Combinação canônica (modificadores em ordem fixa), pronta para comparar."""
    return render(*parse(text))


def validate_map(values: Mapping[str, str]) -> dict[str, str]:
    """Valida as três ações de uma vez, recusando combinações repetidas."""
    if not isinstance(values, Mapping):
        raise _invalid("Formato dos atalhos inválido.")
    unknown = sorted(set(values) - set(HOTKEY_ACTIONS))
    if unknown:
        raise _invalid(f"Ação de atalho desconhecida: {unknown[0]}.")

    normalized: dict[str, str] = {}
    for action in HOTKEY_ACTIONS:
        if action not in values:
            raise _invalid(f"Falta a combinação de {action}.")
        normalized[action] = normalize(values[action])

    seen: dict[str, str] = {}
    for action, combination in normalized.items():
        if combination in seen:
            raise _invalid(f"{combination} está em duas ações ({seen[combination]} e {action}).")
        seen[combination] = action
    return normalized
