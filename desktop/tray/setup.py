"""Diálogo GTK3 de configuração da conexão (primeiro uso e reconfiguração).

Roda no Python do sistema, como a bandeja e o indicador, para o PyGObject não
precisar ser empacotado. O token nunca vem por argumento: o helper grava um
JSON temporário 0600 que o cliente lê e apaga.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

TIMEOUT_S = 8.0


def normalize_url(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if "://" not in text:
        host = text.split("/", 1)[0].split(":", 1)[0].lower()
        scheme = "http" if host in {"localhost", "127.0.0.1", "::1"} else "https"
        text = f"{scheme}://{text}"
    return text.rstrip("/")


def probe(url: str, token: str) -> tuple[bool, str]:
    """Testa ``GET /api/v1/settings`` com Bearer; não revela o token."""
    normalized = normalize_url(url)
    if not normalized:
        return False, "Informe o endereço do servidor."
    if not token.strip():
        return False, "Informe o token para testar."
    request = urllib.request.Request(
        f"{normalized}/api/v1/settings",
        headers={"Authorization": f"Bearer {token.strip()}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            if response.status == 200:
                return True, "Conexão ok."
            return False, f"A API respondeu HTTP {response.status}."
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            return False, "Token recusado. Confira o token e tente de novo."
        return False, f"A API respondeu HTTP {exc.code}."
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return False, f"Não foi possível conectar: {exc}"


def write_result(path: Path, url: str, token: str, autostart: bool) -> None:
    payload = json.dumps(
        {"url": normalize_url(url), "token": token.strip(), "autostart": autostart},
        ensure_ascii=False,
    )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(payload + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Configurar a conexão do VB Typer.")
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--result", required=True)
    parser.add_argument("--autostart", action="store_true")
    parser.add_argument("--token-saved", action="store_true")
    args = parser.parse_args(argv)

    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import GLib, Gtk

    result_path = Path(args.result)
    saved = {"ok": False}

    window = Gtk.Window(title="VB Typer — Configurar conexão")
    window.set_default_size(480, -1)
    window.set_border_width(18)
    window.set_position(Gtk.WindowPosition.CENTER)
    window.set_resizable(False)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    window.add(outer)

    title = Gtk.Label()
    title.set_markup("<b>Conecte o VB Typer</b>")
    title.set_xalign(0)
    outer.pack_start(title, False, False, 0)

    help_text = Gtk.Label(
        label=(
            "Informe o endereço do servidor e o token de acesso.\n"
            "O token fica só neste computador, em um arquivo protegido."
        )
    )
    help_text.set_xalign(0)
    help_text.set_line_wrap(True)
    outer.pack_start(help_text, False, False, 0)

    url_label = Gtk.Label(label="Endereço do servidor")
    url_label.set_xalign(0)
    outer.pack_start(url_label, False, False, 0)
    url_entry = Gtk.Entry()
    url_entry.set_text(args.url)
    url_entry.set_placeholder_text("https://vbtyper.exemplo.com")
    outer.pack_start(url_entry, False, False, 0)

    token_label = Gtk.Label(
        label="Token de acesso"
        + (" (deixe em branco para manter o atual)" if args.token_saved else "")
    )
    token_label.set_xalign(0)
    outer.pack_start(token_label, False, False, 0)
    token_entry = Gtk.Entry()
    token_entry.set_visibility(False)
    token_entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
    token_entry.set_placeholder_text("cole o token aqui")
    outer.pack_start(token_entry, False, False, 0)

    note = Gtk.Label(
        label=(
            "O token é o mesmo arquivo api-token do servidor do VB Typer. "
            "Peça a quem administra a instância, se você não o tiver."
        )
    )
    note.set_xalign(0)
    note.set_line_wrap(True)
    outer.pack_start(note, False, False, 0)

    autostart_check = Gtk.CheckButton(label="Iniciar com o sistema")
    autostart_check.set_active(args.autostart or not args.token_saved)
    outer.pack_start(autostart_check, False, False, 0)

    status = Gtk.Label(label="")
    status.set_xalign(0)
    status.set_line_wrap(True)
    outer.pack_start(status, False, False, 0)

    buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    outer.pack_start(buttons, False, False, 0)
    test_button = Gtk.Button(label="Testar conexão")
    buttons.pack_start(test_button, False, False, 0)
    cancel_button = Gtk.Button(label="Cancelar")
    buttons.pack_end(cancel_button, False, False, 0)
    save_button = Gtk.Button(label="Salvar")
    save_button.set_can_default(True)
    buttons.pack_end(save_button, False, False, 0)
    window.set_default(save_button)

    def set_status(message: str, ok: bool | None = None) -> None:
        if ok is True:
            status.set_text(f"✓ {message}")
        elif ok is False:
            status.set_text(f"⚠ {message}")
        else:
            status.set_text(message)

    def close(exit_code: int) -> int:
        window.destroy()
        Gtk.main_quit()
        return exit_code

    def on_test(_button) -> None:
        url = url_entry.get_text()
        token = token_entry.get_text()
        if not token.strip() and not args.token_saved:
            set_status("Informe o token para testar.", False)
            return
        test_button.set_sensitive(False)
        save_button.set_sensitive(False)
        set_status("Testando…")

        def worker() -> None:
            ok, message = probe(url, token)
            GLib.idle_add(finish, ok, message)

        def finish(ok: bool, message: str) -> bool:
            set_status(message, ok)
            test_button.set_sensitive(True)
            save_button.set_sensitive(True)
            return False

        threading.Thread(target=worker, daemon=True).start()

    def on_save(_button) -> None:
        url = normalize_url(url_entry.get_text())
        token = token_entry.get_text().strip()
        if not url:
            set_status("Informe o endereço do servidor.", False)
            return
        if not token and not args.token_saved:
            set_status("Informe o token de acesso.", False)
            return
        try:
            write_result(result_path, url, token, autostart_check.get_active())
        except OSError as exc:
            set_status(f"Não foi possível salvar: {exc}", False)
            return
        saved["ok"] = True
        close(0)

    def on_cancel(_button=None) -> None:
        close(1)

    def on_destroy(*_args) -> None:
        if not saved["ok"]:
            Gtk.main_quit()

    test_button.connect("clicked", on_test)
    save_button.connect("clicked", on_save)
    cancel_button.connect("clicked", on_cancel)
    window.connect("destroy", on_destroy)
    url_entry.connect("activate", lambda *_: token_entry.grab_focus())
    token_entry.connect("activate", lambda *_: on_save(save_button))

    window.show_all()
    token_entry.grab_focus()
    Gtk.main()
    return 0 if saved["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
