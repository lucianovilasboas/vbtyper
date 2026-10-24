"""Troca de perfil por atalho: ciclo, volta ao padrão e leitura das combinações.

O ciclo é **temporário**: muda o perfil do próximo ditado sem alterar o padrão
gravado no backend. A escolha explícita (bandeja ou interface) limpa o ciclo.

A gramática é a mesma do backend (``ctrl+alt+Tab``); aqui ela é lida sem
depender de plataforma, para poder ser testada fora do X.
"""

from __future__ import annotations

PROFILE_NEXT = "profile_next"
PROFILE_PREVIOUS = "profile_previous"
PROFILE_DEFAULT = "profile_default"

# Passo de cada ação do atalho; o padrão não anda na lista, ele limpa o ciclo.
STEPS = {PROFILE_NEXT: 1, PROFILE_PREVIOUS: -1}

DEFAULT_HOTKEYS: dict[str, str] = {
    PROFILE_NEXT: "ctrl+alt+Tab",
    PROFILE_PREVIOUS: "ctrl+alt+shift+Tab",
    PROFILE_DEFAULT: "ctrl+alt+0",
}

MODIFIERS = ("ctrl", "alt", "shift", "super")


def next_profile(profiles: list[str], current: str, step: int = 1) -> str:
    """Próximo (ou anterior) perfil da lista, dando a volta nas pontas.

    Um perfil atual fora da lista (apagado na interface) recomeça pela ponta na
    direção do passo, para o atalho nunca ficar preso.
    """
    if not profiles:
        return current
    if current not in profiles:
        return profiles[0] if step > 0 else profiles[-1]
    return profiles[(profiles.index(current) + step) % len(profiles)]


def parse_hotkey(text: str) -> tuple[tuple[str, ...], str] | None:
    """Separa modificadores e tecla; ``None`` quando a combinação não serve.

    Aceita o mesmo formato do backend. A validação de verdade é do servidor; aqui
    só se recusa o que não daria grab (sem modificador, tecla vazia).
    """
    raw = (text or "").strip()
    if not raw:
        return None
    parts = [part.strip() for part in raw.split("+")]
    if len(parts) < 2 or any(not part for part in parts):
        return None
    *raw_modifiers, raw_key = parts
    modifiers = [part.casefold() for part in raw_modifiers]
    if any(name not in MODIFIERS for name in modifiers):
        return None
    if len(set(modifiers)) != len(modifiers):
        return None
    if "ctrl" in modifiers and "super" in modifiers:
        # Ctrl+Super é o atalho de gravar; um perfil ali começaria um ditado.
        return None
    return tuple(name for name in MODIFIERS if name in modifiers), raw_key


def bindings(hotkeys: dict[str, str]) -> dict[str, tuple[tuple[str, ...], str]]:
    """Combinações válidas para o observador; o que não servir fica de fora."""
    parsed: dict[str, tuple[tuple[str, ...], str]] = {}
    for action, text in (hotkeys or {}).items():
        if action not in (*STEPS, PROFILE_DEFAULT):
            continue
        combination = parse_hotkey(text)
        if combination is not None:
            parsed[action] = combination
    return parsed
