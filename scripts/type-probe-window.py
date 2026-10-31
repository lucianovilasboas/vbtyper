"""Janela descartável do ``type-probe``: recebe a digitação e grava o que chegou.

Roda com o Python do sistema (é ele que tem PyGObject), como os helpers da
bandeja. Não faz parte do cliente: existe só para medir, numa sessão real, se a
inserção entrega o texto na ordem certa.

Uso (chamado pelo ``type-probe.py``, não à mão):

    /usr/bin/python3 type-probe-window.py <saida.txt> <xid.txt> [segundos]
"""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402 - exige require_version antes


def main() -> int:
    if len(sys.argv) < 3:
        print("uso: type-probe-window.py <saida.txt> <xid.txt> [segundos]", file=sys.stderr)
        return 2
    output, xid_file = sys.argv[1], sys.argv[2]
    seconds = float(sys.argv[3]) if len(sys.argv) > 3 else 4.0

    window = Gtk.Window(title="VB Typer — teste de digitação")
    view = Gtk.TextView()
    view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    window.add(view)
    window.set_default_size(760, 220)
    window.show_all()
    window.present()
    view.grab_focus()

    area = window.get_window()
    if area is None:  # pragma: no cover - não deveria acontecer com GTK mapeado
        print("janela sem área X", file=sys.stderr)
        return 1
    with open(xid_file, "w", encoding="utf-8") as handle:
        handle.write(str(area.get_xid()))

    def dump() -> bool:
        buffer = view.get_buffer()
        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
        with open(output, "w", encoding="utf-8") as handle:
            handle.write(text)
        Gtk.main_quit()
        return False

    GLib.timeout_add(int(seconds * 1000), dump)
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
