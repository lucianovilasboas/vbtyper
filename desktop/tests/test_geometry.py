"""Posição do indicador: cálculo puro, sem X e sem GTK."""

from __future__ import annotations

from vb_typer_desktop.geometry import (
    Rect,
    clamp,
    indicator_rect,
    indicator_size,
    place,
)

WINDOW = Rect(100, 200, 900, 600)
SCREEN = Rect(0, 0, 1920, 1080)


def test_indicator_size_is_wider_than_tall():
    width, height = indicator_size(40)
    assert height == 40 and width > height


def test_bottom_center_sits_inside_the_window_with_margin():
    box = place(WINDOW, "bottom-center", 120, 40, margin=10)
    assert box.width == 120 and box.height == 40
    assert box.x == WINDOW.x + (WINDOW.width - 120) // 2
    assert box.bottom == WINDOW.bottom - 10


def test_bottom_left_and_right_hug_the_corners():
    left = place(WINDOW, "bottom-left", 120, 40, margin=10)
    right = place(WINDOW, "bottom-right", 120, 40, margin=10)
    assert left.x == WINDOW.x + 10
    assert right.right == WINDOW.right - 10
    assert left.bottom == right.bottom == WINDOW.bottom - 10


def test_top_center_sits_below_the_top_edge():
    box = place(WINDOW, "top-center", 120, 40, margin=10)
    assert box.y == WINDOW.y + 10


def test_unknown_position_falls_back_to_bottom_center():
    box = place(WINDOW, "qualquer", 120, 40, margin=10)
    assert box.x == WINDOW.x + (WINDOW.width - 120) // 2


def test_clamp_keeps_the_box_on_screen():
    outside = Rect(-500, -500, 120, 40)
    assert clamp(outside, SCREEN) == Rect(0, 0, 120, 40)
    far = Rect(5000, 5000, 120, 40)
    assert clamp(far, SCREEN) == Rect(SCREEN.right - 120, SCREEN.bottom - 40, 120, 40)


def test_clamp_does_not_break_on_a_smaller_screen():
    box = clamp(Rect(10, 10, 400, 300), Rect(0, 0, 200, 100))
    assert box.x == 0 and box.y == 0


def test_window_anchor_needs_a_window():
    assert indicator_rect("window", "bottom-center", 40, window=None, screen=SCREEN) is None


def test_window_anchor_uses_the_focused_window():
    box = indicator_rect("window", "bottom-center", 40, window=WINDOW, screen=SCREEN)
    assert box is not None
    assert WINDOW.y <= box.y < WINDOW.bottom


def test_screen_anchor_ignores_the_window():
    box = indicator_rect("screen", "bottom-center", 40, window=WINDOW, screen=SCREEN)
    assert box is not None and box.bottom == SCREEN.bottom - 12


def test_pointer_anchor_sits_below_the_pointer():
    box = indicator_rect("pointer", "bottom-center", 40, pointer=(400, 300), screen=SCREEN)
    assert box is not None
    assert box.y > 300
    assert box.x + box.width // 2 == 400


def test_pointer_anchor_without_pointer_is_ignored():
    box = indicator_rect("pointer", "bottom-center", 40, pointer=None, screen=SCREEN)
    assert box is None


def test_window_partly_off_screen_is_clamped():
    off = Rect(-40, -30, 900, 600)
    box = indicator_rect("window", "bottom-left", 40, window=off, screen=SCREEN)
    assert box is not None and box.x >= 0 and box.y >= 0
