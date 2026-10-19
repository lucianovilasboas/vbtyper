"""Contrato dos adaptadores de sistema operacional."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Protocol


class HotkeyWatcher(Protocol):
    """Observador do atalho global; precisa parar de forma determinística."""

    @property
    def running(self) -> bool:
        """Indica se o observador está ativo."""

    def start(self) -> None:
        """Começa a observar as teclas do atalho."""

    def stop(self) -> None:
        """Para de observar; ao retornar, nenhum evento novo é entregue."""


class Platform(Protocol):
    """Integrações locais que cada sistema operacional implementa."""

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
