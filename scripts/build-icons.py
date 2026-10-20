"""Gera os ícones do VB Typer a partir da marca original (`vb-typer.png`).

Uso (não é dependência do projeto, só desta ferramenta):

    uv run --with pillow scripts/build-icons.py

Escreve:
  * `desktop/assets/tray_*.png` — bandeja, uma cor por estado;
  * `web/static/logo.png` e `web/static/favicon.png` — telas do app.

A marca é uma fita roxa com transparência. Para os estados da bandeja a
luminância da fita é remapeada para a cor do estado, preservando o relevo; o
estado "ativo" mantém as cores originais.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "vb-typer.png"
TRAY_DIR = ROOT / "desktop" / "assets"
WEB_DIR = ROOT / "web" / "static"

TRAY_SIZE = 64  # os ícones são 64x64; o painel reduz para ~22
MARGIN_RATIO = 0.03

# Rampas (escura, clara) por estado. `on` é a própria marca.
RAMPS = {
    "off": ((127, 29, 29), (248, 113, 113)),        # vermelho: ditado desativado
    "rec": ((167, 139, 250), (245, 235, 255)),      # lilás claro: pulsa no gravando
    "busy": ((124, 45, 18), (253, 186, 116)),       # laranja: transcrevendo
    "busy_alt": ((154, 52, 18), (254, 215, 170)),   # laranja claro: pulso
}


def square_mark(image: Image.Image) -> Image.Image:
    """Recorta na marca e devolve um quadrado com uma margem pequena."""
    box = image.getbbox()
    if box is None:
        raise SystemExit(f"A marca em {SOURCE} está vazia (sem pixels visíveis).")
    left, top, right, bottom = box
    width, height = right - left, bottom - top
    side = max(width, height)
    margin = round(side * MARGIN_RATIO)
    canvas = Image.new("RGBA", (side + 2 * margin,) * 2, (0, 0, 0, 0))
    canvas.paste(image.crop(box), ((side - width) // 2 + margin, (side - height) // 2 + margin))
    return canvas


def tint(mark: Image.Image, low: tuple[int, int, int], high: tuple[int, int, int]) -> Image.Image:
    """Remapeia a luminância da marca para uma rampa de duas cores."""
    source = mark.load()
    result = mark.copy()
    target = result.load()
    width, height = mark.size
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = source[x, y]
            if not alpha:
                continue
            level = (0.299 * red + 0.587 * green + 0.114 * blue) / 255.0
            target[x, y] = (
                round(low[0] + (high[0] - low[0]) * level),
                round(low[1] + (high[1] - low[1]) * level),
                round(low[2] + (high[2] - low[2]) * level),
                alpha,
            )
    return result


def main() -> int:
    if not SOURCE.is_file():
        print(f"Falta a marca: {SOURCE}", file=sys.stderr)
        return 1
    mark = square_mark(Image.open(SOURCE).convert("RGBA"))
    TRAY_DIR.mkdir(parents=True, exist_ok=True)
    WEB_DIR.mkdir(parents=True, exist_ok=True)

    tray = mark.resize((TRAY_SIZE, TRAY_SIZE), Image.LANCZOS)
    tray.save(TRAY_DIR / "tray_on.png")
    print(f"desktop/assets/tray_on.png ({TRAY_SIZE}x{TRAY_SIZE}, marca original)")
    for name, (low, high) in RAMPS.items():
        tint(tray, low, high).save(TRAY_DIR / f"tray_{name}.png")
        print(f"desktop/assets/tray_{name}.png (rampa {low} -> {high})")

    # Ícone do aplicativo: usado pela entrada do menu (.desktop).
    mark.resize((256, 256), Image.LANCZOS).save(TRAY_DIR / "logo.png")
    print("desktop/assets/logo.png (256x256, entrada do menu)")

    mark.resize((128, 128), Image.LANCZOS).save(WEB_DIR / "logo.png")
    mark.resize((32, 32), Image.LANCZOS).save(WEB_DIR / "favicon.png")
    print("web/static/logo.png (128x128) e web/static/favicon.png (32x32)")

    # PWA: "any" para a tela inicial e "maskable" para o Android, que recorta
    # até ~20% das bordas — por isso a marca ocupa menos espaço nesse último.
    background = (250, 250, 253, 255)  # --bg do tema claro
    for size in (192, 512):
        icon = Image.new("RGBA", (size, size), background)
        inner = mark.resize((int(size * 0.86),) * 2, Image.LANCZOS)
        icon.paste(inner, ((size - inner.width) // 2,) * 2, inner)
        icon.save(WEB_DIR / f"icon-{size}.png")
        print(f"web/static/icon-{size}.png ({size}x{size})")

    maskable = Image.new("RGBA", (512, 512), background)
    inner = mark.resize((int(512 * 0.72),) * 2, Image.LANCZOS)
    maskable.paste(inner, ((512 - inner.width) // 2,) * 2, inner)
    maskable.save(WEB_DIR / "icon-maskable-512.png")
    print("web/static/icon-maskable-512.png (512x512, zona segura do Android)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
