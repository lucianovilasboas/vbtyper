"""Posição do indicador visual: cálculo puro, sem X e sem GTK."""

from __future__ import annotations

from dataclasses import dataclass

ANCHORS = ("window", "screen", "pointer")
POSITIONS = ("bottom-center", "bottom-left", "bottom-right", "top-center")
MARGIN = 12
WIDTH_RATIO = 3
POINTER_GAP = 24


@dataclass(frozen=True)
class Rect:
    """Retângulo em coordenadas da raiz da tela."""

    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


def indicator_size(size: int) -> tuple[int, int]:
    """Largura e altura do painel; ``size`` é a altura em pixels."""
    return size * WIDTH_RATIO, size


def place(rect: Rect, position: str, width: int, height: int, margin: int = MARGIN) -> Rect:
    """Posiciona uma caixa ``width x height`` dentro de ``rect``, com margem."""
    if position == "bottom-left":
        x = rect.x + margin
        y = rect.bottom - height - margin
    elif position == "bottom-right":
        x = rect.right - width - margin
        y = rect.bottom - height - margin
    elif position == "top-center":
        x = rect.x + (rect.width - width) // 2
        y = rect.y + margin
    else:  # bottom-center
        x = rect.x + (rect.width - width) // 2
        y = rect.bottom - height - margin
    return Rect(x, y, width, height)


def clamp(box: Rect, screen: Rect) -> Rect:
    """Mantém a caixa dentro da tela (sem estourar as bordas)."""
    x = min(max(box.x, screen.x), max(screen.x, screen.right - box.width))
    y = min(max(box.y, screen.y), max(screen.y, screen.bottom - box.height))
    return Rect(x, y, box.width, box.height)


def indicator_rect(
    anchor: str,
    position: str,
    size: int,
    *,
    window: Rect | None = None,
    screen: Rect | None = None,
    pointer: tuple[int, int] | None = None,
) -> Rect | None:
    """Caixa do indicador, ou ``None`` quando não há onde ancorar.

    ``window`` é ``None`` quando não há janela em foco — por exemplo em tela
    cheia, onde o indicador não deve aparecer.
    """
    width, height = indicator_size(size)
    if anchor == "pointer" and pointer is not None:
        box = Rect(pointer[0] - width // 2, pointer[1] + POINTER_GAP, width, height)
    elif anchor == "screen" and screen is not None:
        box = place(screen, position, width, height, MARGIN)
    elif window is not None:
        box = place(window, position, width, height, MARGIN)
    else:
        return None
    return clamp(box, screen) if screen is not None else box
