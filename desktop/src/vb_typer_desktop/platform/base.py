"""Contrato dos adaptadores de sistema operacional."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Protocol

from vb_typer_desktop.geometry import Rect

# Combinação já separada: (("ctrl", "alt"), "Tab").
HotkeyBindings = dict[str, tuple[tuple[str, ...], str]]


class HotkeyWatcher(Protocol):
    """Observador do atalho global; precisa parar de forma determinística."""

    @property
    def running(self) -> bool:
        """Indica se o observador está ativo."""

    def start(self) -> None:
        """Começa a observar as teclas do atalho."""

    def stop(self) -> None:
        """Para de observar; ao retornar, nenhum evento novo é entregue."""


class ComboWatcher(Protocol):
    """Combinações de perfil; capacidade opcional de cada sistema."""

    @property
    def running(self) -> bool:
        """Indica se o observador está ativo."""

    def start(self) -> None:
        """Registra as combinações."""

    def stop(self) -> None:
        """Libera as combinações; idempotente."""


class Platform(Protocol):
    """Integrações locais que cada sistema operacional implementa.

    ``combo_watcher(bindings, on_action, on_error)`` é **opcional**: quem ainda
    não portou a troca de perfil por atalho simplesmente não o implementa, e o
    daemon mantém o ditado funcionando sem ela.
    """

    name: str

    def ensure_session(self) -> None:
        """Valida que o ambiente gráfico suportado está disponível."""

    def active_window(self) -> int | None:
        """Identifica a janela que deve receber o texto ditado."""

    def type_text(
        self, text: str, target: int | None, cancel: threading.Event | None = None
    ) -> None:
        """Insere ``text`` no ponto do cursor da janela ``target``."""

    def hotkey_watcher(self, on_change: Callable[[str, bool], None]) -> HotkeyWatcher:
        """Cria o observador do atalho, avisando ``on_change(grupo, pressionada)``."""

    def window_rect(self, window: int | None) -> Rect | None:
        """Área da janela de topo; ``None`` quando não há onde ancorar o indicador."""

    def screen_rect(self) -> Rect | None:
        """Área da tela em coordenadas da raiz."""

    def pointer_position(self) -> tuple[int, int] | None:
        """Posição do ponteiro em coordenadas da raiz."""
