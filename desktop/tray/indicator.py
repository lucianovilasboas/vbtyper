"""Indicador visual do ditado: onda do microfone perto da janela em foco.

Roda no Python do sistema (PyGObject/GTK3), como a bandeja, e conversa com o
cliente pelo socket de controle. Quem decide *onde* e *de que tamanho* é o
cliente; aqui só se desenha. O painel não rouba foco e deixa os cliques
atravessarem, para nunca atrapalhar o aplicativo em uso.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import socket
import sys
import time

BARS = 14
# Enquanto o painel está visível a consulta é rápida; ocioso, ele é econômico.
# 60 ms é o limite de quanto o painel pode demorar a aparecer após o atalho.
POLL_VISIBLE_MS = 45
POLL_IDLE_MS = 60
FRAME_MS = 40
# Constante de tempo do ataque, em segundos: sobe quase junto com a voz.
ATTACK_S = 0.035
# O retorno é **linear**, em pontos de nível por segundo. Uma exponencial deixa
# uma cauda longa nos últimos por centos — o trecho que se percebe como lentidão
# ("escorrendo"), por mais rápida que seja a constante.
FALL_PER_SECOND = 350.0
# Abaixo disto, com a voz parada, a barra zera de vez em vez de rastejar.
FLOOR = 4.0
FADE_STEP = 0.30
HIDE_POLLS = 3
FAILS_TO_QUIT = 12
# Nível de microfone que já desenha a barra mais alta. Com este microfone a fala
# normal pica entre 5% e 45%, então o topo fica logo acima disso.
FULL_LEVEL = 36.0
# Curva aplicada ao nível: levanta a faixa média, para a onda "sentir" mais.
GAMMA = 0.75
DEBUG_PATH = os.environ.get("VB_TYPER_INDICATOR_DEBUG")

# A onda usa o roxo de destaque do app (o mesmo `accent` do 1.x).
LILAC_PALE = (0.85, 0.80, 1.00)
LILAC = (0.65, 0.48, 1.00)
PURPLE = (0.42, 0.16, 0.88)
GREEN = (0.06, 0.63, 0.40)
ORANGE = (0.93, 0.55, 0.10)
RED = (0.85, 0.22, 0.22)
# Contorno fino e escuro: mantém as formas legíveis sobre qualquer fundo.
SHADOW = (0.04, 0.02, 0.10, 0.45)
# Trilho da barra de nível: discreto, mas visível no silêncio (senão o painel
# parece não ter começado).
TRACK = (0.42, 0.20, 0.86, 0.34)
# Gradiente da barra de nível. A onda começa num lilás quase branco (as barras
# curtas ficam leves), mas numa barra única isso deixava a barra cheia pálida.
BAR_TOP = (0.58, 0.40, 1.00)
BAR_BOTTOM = (0.38, 0.13, 0.86)
# Altura da barra de nível, como fração da altura do painel.
BAR_RATIO = 0.30
SHAPES = ("bar", "wave")
PHASES = ("recording", "processing", "inserted", "error")


def _mix(first, second, ratio: float) -> tuple[float, float, float]:
    return (
        first[0] + (second[0] - first[0]) * ratio,
        first[1] + (second[1] - first[1]) * ratio,
        first[2] + (second[2] - first[2]) * ratio,
    )


def fill_width(ratio: float, width: float, minimum: float) -> float:
    """Largura do preenchimento da barra: proporcional, com um mínimo visível.

    O mínimo (a própria altura da barra) evita que, num nível baixinho, sobre
    apenas um risco invisível de um pixel.
    """
    clamped = min(1.0, max(0.0, ratio))
    if clamped <= 0.0:
        return 0.0
    return max(minimum, clamped * width)


class Levels:
    """Histórico de níveis suavizados, para a onda acompanhar a fala sem tremer.

    Sobe com constante de tempo curta (responde junto com a voz) e **desce em
    linha reta**: cada quadro cai a mesma quantidade, então a barra chega ao
    fundo sem o rastejo final de uma exponencial.
    """

    def __init__(
        self,
        bars: int = BARS,
        attack_s: float = ATTACK_S,
        fall_rate: float = FALL_PER_SECOND,
    ) -> None:
        self.bars = bars
        self.attack_s = attack_s
        self.fall_rate = fall_rate
        self.shown = 0.0
        self.values = [0.0] * bars

    def push(self, target, elapsed: float = FRAME_MS / 1000) -> None:
        """Aproxima do alvo num intervalo de ``elapsed`` segundos."""
        goal = max(0.0, min(100.0, float(target)))
        elapsed = max(0.0, float(elapsed))
        if goal >= self.shown:
            factor = 1.0 if self.attack_s <= 0 else 1.0 - math.exp(-elapsed / self.attack_s)
            self.shown += (goal - self.shown) * factor
        else:
            self.shown = max(goal, self.shown - self.fall_rate * elapsed)
            if goal < FLOOR and self.shown < FLOOR:
                self.shown = 0.0
        self.values.append(self.shown)
        del self.values[: -self.bars]


def _debug(message: str) -> None:
    """Diagnóstico opcional do helper (que não tem terminal para reclamar)."""
    if not DEBUG_PATH:
        return
    with contextlib.suppress(OSError), open(DEBUG_PATH, "a", encoding="utf-8") as handle:
        handle.write(f"{time.monotonic():.3f} {message}\n")


def _rounded(cr, x, y, width, height, radius) -> None:
    radius = min(radius, width / 2, height / 2)
    cr.new_sub_path()
    cr.arc(x + width - radius, y + radius, radius, -math.pi / 2, 0)
    cr.arc(x + width - radius, y + height - radius, radius, 0, math.pi / 2)
    cr.arc(x + radius, y + height - radius, radius, math.pi / 2, math.pi)
    cr.arc(x + radius, y + radius, radius, math.pi, 3 * math.pi / 2)
    cr.close_path()


def phase_from_state(state: dict) -> str:
    """Fase do indicador; aceita snapshots antigos, sem o campo ``phase``."""
    phase = state.get("phase")
    if phase in PHASES:
        return phase
    if state.get("recording"):
        return "recording"
    if state.get("state") == "processing":
        return "processing"
    return "idle"


class Indicator:
    """Painel flutuante com a onda do microfone e o andamento da transcrição."""

    def __init__(
        self,
        socket_path: str,
        speed: float = 1.0,
        sensitivity: float = 1.0,
        shape: str = "bar",
    ) -> None:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk, GLib, Gtk

        self.GLib = GLib
        self.Gtk = Gtk
        self.socket_path = socket_path
        self.speed = max(0.2, speed)
        self.sensitivity = max(0.2, sensitivity)
        self.shape = shape if shape in SHAPES else "bar"
        self.levels = Levels(attack_s=ATTACK_S / self.speed, fall_rate=FALL_PER_SECOND * self.speed)
        self.phase = "idle"
        self.level = 0
        self._alpha = 1.0
        self.box: tuple[int, int, int, int] | None = None
        self.position: tuple[int, int] | None = None
        self.size: tuple[int, int] | None = None
        self.opacity = 0.0
        self.visible = False
        self.fails = 0
        self.idle_ticks = 0
        self.next_poll = 0.0

        window = Gtk.Window(type=Gtk.WindowType.POPUP)
        window.set_decorated(False)
        window.set_resizable(False)
        window.set_skip_taskbar_hint(True)
        window.set_skip_pager_hint(True)
        window.set_accept_focus(False)
        window.set_focus_on_map(False)
        window.set_keep_above(True)
        window.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
        window.set_app_paintable(True)
        screen = window.get_screen()
        visual = screen.get_rgba_visual()
        self.composited = bool(visual and screen.is_composited())
        if visual:
            window.set_visual(visual)
        self.area = Gtk.DrawingArea()
        self.area.connect("draw", self._draw)
        window.add(self.area)
        window.realize()
        self._click_through()
        window.hide()
        self.window = window

    # ------------------------------------------------------------- entrada

    def _click_through(self) -> None:
        """Cliques atravessam o painel: ele nunca rouba um clique do aplicativo."""
        try:
            import cairo

            gdk_window = self.window.get_window()
            if gdk_window is not None:
                gdk_window.input_shape_combine_region(cairo.Region(), 0, 0)
        except Exception:
            pass

    def _talk(self) -> dict | None:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(1.0)
                client.connect(self.socket_path)
                client.sendall(b'{"cmd": "state"}\n')
                data = client.recv(8192)
        except OSError:
            return None
        if not data:
            return None
        try:
            return json.loads(data.decode() or "{}")
        except ValueError:
            return None

    # ------------------------------------------------------------- estado

    def apply(self, state: dict) -> None:
        self.phase = phase_from_state(state)
        self.level = int(state.get("level") or 0)
        box = state.get("indicator")
        self.box = None
        if isinstance(box, dict):
            with contextlib.suppress(KeyError, TypeError, ValueError):
                self.box = (int(box["x"]), int(box["y"]), int(box["w"]), int(box["h"]))
        _debug(f"estado fase={self.phase} nivel={self.level} caixa={self.box}")

    def _show(self) -> None:
        if self.box is None:
            return
        x, y, width, height = self.box
        size = (width, height)
        if size != self.size:
            # A janela é POPUP e se dimensiona pelo pedido do filho: sem isto o
            # GTK mapeia num tamanho padrão e o painel sai gigante.
            self.size = size
            self.area.set_size_request(width, height)
            self.window.resize(width, height)
            _debug(f"redimensiona para {size}")
        if not self.visible:
            self.window.show_all()
            self.window.move(x, y)
            self.window.resize(width, height)
            self.visible = True
            # Aparece já visível: reação imediata ao atalho, sem fade de entrada.
            self.opacity = 1.0
            self.position = (x, y)
            _debug(f"mostra em {(x, y)} {size}")
        elif (x, y) != self.position:
            self.window.move(x, y)
            self.position = (x, y)
            _debug(f"move para {(x, y)}")
        self._opacity(1.0)

    def _hide(self) -> None:
        if not self.visible:
            return
        if self._opacity(0.0):
            self.window.hide()
            self.visible = False

    def _opacity(self, target: float) -> bool:
        """Aproxima o valor do alvo; devolve se já chegou lá.

        O esmaecimento é feito no desenho (alpha do cairo), não em
        ``set_opacity``: assim funciona sem compositor e sem API depreciada.
        """
        step = FADE_STEP if target > self.opacity else -FADE_STEP
        self.opacity = max(0.0, min(1.0, self.opacity + step))
        return abs(self.opacity - target) < FADE_STEP

    # ------------------------------------------------------------- ciclo

    def tick(self) -> bool:
        now = time.monotonic()
        interval = POLL_VISIBLE_MS if self.visible else POLL_IDLE_MS
        if now >= self.next_poll:
            self.next_poll = now + interval / 1000
            state = self._talk()
            if state is None:
                self.fails += 1
                if self.fails >= FAILS_TO_QUIT:
                    self.Gtk.main_quit()
                    return False
            else:
                self.fails = 0
                self.apply(state)

        if self.phase == "recording":
            self.levels.push(self.level)
        else:
            self.levels.push(0)
            if self.phase != "processing":
                self.level = 0

        if self.phase == "idle" or self.box is None:
            self.idle_ticks += 1
            if self.idle_ticks >= HIDE_POLLS:
                self._hide()
                return True
        else:
            self.idle_ticks = 0
            self._show()
        self.area.queue_draw()
        return True

    def start(self) -> int:
        self.next_poll = 0.0
        self.tick()
        self.GLib.timeout_add(FRAME_MS, self.tick)
        self.Gtk.main()
        return 0

    # ------------------------------------------------------------- desenho

    def _draw(self, area, cr) -> bool:
        allocation = area.get_allocation()
        width, height = allocation.width, allocation.height
        self._alpha = max(0.08, self.opacity)
        if self.phase == "recording":
            if self.shape == "wave":
                self._draw_wave(cr, width, height)
            else:
                self._draw_level_bar(cr, width, height)
        elif self.phase == "processing":
            self._draw_sweep(cr, width, height)
        elif self.phase == "inserted":
            self._draw_check(cr, width, height)
        else:
            self._draw_warning(cr, width, height)
        return False

    def _level_ratio(self, value) -> float:
        """Nível do microfone já achatado na curva que a gente calibrou."""
        return min(1.0, max(0.0, (value / FULL_LEVEL) ** GAMMA * self.sensitivity))

    def _draw_level_bar(self, cr, width, height) -> None:
        """Trilho fixo com preenchimento que cresce para a direita, como na web.

        A fase "transcrevendo" também é uma barra horizontal, então aqui a barra
        fica **ancorada à esquerda** e o preenchimento indica o nível — o
        movimento (crescer) é o que a distingue do segmento que desliza.
        """
        import cairo

        bar_height = max(8.0, height * BAR_RATIO)
        top = (height - bar_height) / 2
        radius = bar_height / 2

        _rounded(cr, 0.5, top, width - 1, bar_height, radius)
        cr.set_source_rgba(TRACK[0], TRACK[1], TRACK[2], TRACK[3] * self._alpha)
        cr.fill_preserve()
        cr.set_source_rgba(SHADOW[0], SHADOW[1], SHADOW[2], SHADOW[3] * self._alpha)
        cr.set_line_width(1.0)
        cr.stroke()

        ratio = self._level_ratio(self.levels.shown)
        fill = fill_width(ratio, width - 1, bar_height)
        if fill <= 0:
            return
        cr.save()
        _rounded(cr, 0.5, top, width - 1, bar_height, radius)
        cr.clip()
        gradient = cairo.LinearGradient(0, top, 0, top + bar_height)
        gradient.add_color_stop_rgba(0, *BAR_TOP, self._alpha)
        gradient.add_color_stop_rgba(1, *BAR_BOTTOM, self._alpha)
        _rounded(cr, 0.5, top, fill, bar_height, radius)
        cr.set_source(gradient)
        cr.fill()
        cr.restore()

    def _paint(self, cr, source) -> None:
        """Preenche o caminho atual e contorna com um traço escuro fino."""
        if isinstance(source, tuple):
            cr.set_source_rgba(*source, self._alpha)
        else:
            cr.set_source(source)
        cr.fill_preserve()
        cr.set_source_rgba(SHADOW[0], SHADOW[1], SHADOW[2], SHADOW[3] * self._alpha)
        cr.set_line_width(1.0)
        cr.stroke()

    def _stroke(self, cr, colour, width) -> None:
        """Traça o caminho atual com sombra por baixo, para dar contraste."""
        cr.set_line_cap(1)
        cr.set_source_rgba(SHADOW[0], SHADOW[1], SHADOW[2], SHADOW[3] * self._alpha)
        cr.set_line_width(width + 2.5)
        cr.stroke_preserve()
        cr.set_source_rgba(*colour, self._alpha)
        cr.set_line_width(width)
        cr.stroke()

    def _draw_wave(self, cr, width, height) -> None:
        import cairo

        values = self.levels.values
        slot = width / (len(values) + 1)
        bar_width = max(2.5, slot * 0.45)
        middle = height / 2
        ceiling = (height - 6) / 2
        for index, value in enumerate(values):
            ratio = self._level_ratio(value)
            amplitude = max(height * 0.10, ratio * ceiling)
            top = middle - amplitude
            bar = amplitude * 2
            gradient = cairo.LinearGradient(0, top, 0, top + bar)
            gradient.add_color_stop_rgba(0, *_mix(LILAC_PALE, LILAC, ratio), self._alpha)
            gradient.add_color_stop_rgba(1, *_mix(LILAC, PURPLE, ratio), self._alpha)
            x = slot * (index + 1) - bar_width / 2
            _rounded(cr, x, top, bar_width, bar, bar_width / 2)
            self._paint(cr, gradient)

    def _draw_sweep(self, cr, width, height) -> None:
        progress = (time.monotonic() * 0.8) % 2.0
        position = progress if progress <= 1 else 2 - progress
        bar_width = width * 0.22
        _rounded(
            cr,
            (width - bar_width) * position,
            height * 0.3,
            bar_width,
            height * 0.4,
            height * 0.2,
        )
        self._paint(cr, ORANGE)

    def _draw_check(self, cr, width, height) -> None:
        cr.move_to(width * 0.38, height * 0.52)
        cr.line_to(width * 0.46, height * 0.64)
        cr.line_to(width * 0.64, height * 0.36)
        self._stroke(cr, GREEN, max(3.0, height * 0.11))

    def _draw_warning(self, cr, width, height) -> None:
        centre = width / 2
        cr.move_to(centre, height * 0.28)
        cr.line_to(centre, height * 0.6)
        self._stroke(cr, RED, max(3.0, height * 0.11))
        cr.arc(centre, height * 0.76, max(2.0, height * 0.06), 0, 2 * math.pi)
        self._paint(cr, RED)


def _tuning(raw: str, default: float) -> float:
    try:
        return min(3.0, max(0.5, float(raw)))
    except ValueError:
        return default


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    socket_path: str | None = None
    speed = 1.0
    sensitivity = 1.0
    shape = "bar"
    for item in arguments:
        if item.startswith("--speed="):
            speed = _tuning(item.partition("=")[2], speed)
        elif item.startswith("--sensitivity="):
            sensitivity = _tuning(item.partition("=")[2], sensitivity)
        elif item.startswith("--shape="):
            candidate = item.partition("=")[2]
            if candidate in SHAPES:
                shape = candidate
        elif not item.startswith("--"):
            socket_path = item
    if socket_path is None:
        print(
            "uso: indicator.py <socket de controle> [--speed=N] [--sensitivity=N] "
            "[--shape=bar|wave]",
            file=sys.stderr,
        )
        return 2
    return Indicator(socket_path, speed=speed, sensitivity=sensitivity, shape=shape).start()


if __name__ == "__main__":
    raise SystemExit(main())
