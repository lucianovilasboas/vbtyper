"""Atalho global: segurar Ctrl+Super inicia; soltar qualquer uma encerra.

O adaptador de plataforma traduz as teclas do sistema para os grupos ``ctrl`` e
``super``; toda a lógica do atalho fica aqui, sem depender do sistema.
"""

from __future__ import annotations


class HotkeyState:
    """Máquina de estados pura: Ctrl+Super inicia; soltar qualquer uma encerra."""

    def __init__(self) -> None:
        self.pressed: set[str] = set()
        self.recording = False

    def feed(self, group: str | None, is_press: bool) -> str | None:
        if group not in {"ctrl", "super"}:
            return None
        if is_press:
            self.pressed.add(group)
            if self.pressed == {"ctrl", "super"} and not self.recording:
                self.recording = True
                return "start"
        else:
            self.pressed.discard(group)
            if self.recording and self.pressed != {"ctrl", "super"}:
                self.recording = False
                return "stop"
        return None
