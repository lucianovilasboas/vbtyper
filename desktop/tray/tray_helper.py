"""Bandeja do sistema para o VB Typer (processo auxiliar GTK3).

Roda com o Python do sistema (/usr/bin/python3), que tem PyGObject e
AyatanaAppIndicator3. Conversa com o app por um socket Unix local.

Cores do ícone:
  * ditado desativado -> vermelho
  * ditado ativo      -> verde
  * gravando          -> pisca (verde/claro) e volta à cor anterior ao soltar
"""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

POLL_MS = 400
BUSY_BLINK_MS = 180
ICON_FALLBACK = "audio-input-microphone"


def icon_name(dictating: bool, recording: bool, blink: bool = False,
              processing: bool = False, busy_alt: bool = False) -> str:
    """Verde = ditado ativo, vermelho = desativado, pisca gravando,
    laranja piscando (mais rápido) enquanto transcreve."""
    if processing:
        return "tray_busy_alt" if busy_alt else "tray_busy"
    if recording:
        return "tray_rec" if blink else "tray_on"
    return "tray_on" if dictating else "tray_off"


PROFILE_MARK = " ✓"


def profile_label(name: str, active: bool) -> str:
    """Rótulo de um perfil: o vigente é marcado no próprio texto."""
    return f"{name}{PROFILE_MARK}" if active else name


def profile_signature(profiles) -> tuple[tuple[str, str], ...]:
    """Pares ``(slug, nome)`` na ordem exibida — a chave de "a lista mudou"."""
    signature = []
    for item in profiles or ():
        if not isinstance(item, dict):
            continue
        slug = str(item.get("slug") or "").strip()
        if not slug:
            continue
        signature.append((slug, str(item.get("name") or slug)))
    return tuple(signature)


class Tray:
    def __init__(self, socket_path: str, assets: Path) -> None:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import GLib, Gtk
        from gi.repository import AyatanaAppIndicator3 as AppIndicator

        self.GLib = GLib
        self.Gtk = Gtk
        self.AppIndicator = AppIndicator
        self.socket_path = socket_path
        self.assets = assets
        self.last_state = ""
        self.blink = False
        self.processing = False
        self.busy_alt = False
        self.indicator = self.AppIndicator.Indicator.new(
            "vb-typer", ICON_FALLBACK, self.AppIndicator.IndicatorCategory.APPLICATION_STATUS
        )
        self.indicator.set_status(self.AppIndicator.IndicatorStatus.ACTIVE)
        self.indicator.set_title("VB Typer")

        self.menu = self.Gtk.Menu()
        self.open_item = self.Gtk.MenuItem(label="Abrir configurações")
        self.open_item.connect("activate", lambda *_: self.send("show"))
        self.open_item.show()
        self.menu.append(self.open_item)

        self.toggle_item = self.Gtk.MenuItem(label="Iniciar ditado")
        self.toggle_item.connect("activate", lambda *_: self.send("toggle"))
        self.toggle_item.show()
        self.menu.append(self.toggle_item)

        # --- acrescentado no 2.0: perfis de texto na bandeja ---
        # Itens simples, com o perfil vigente marcado no próprio rótulo. Itens de
        # rádio foram descartados: o host do AppIndicator constrói o menu no
        # primeiro uso e ativava um item sozinho, trocando a escolha sem clique.
        self.menu.append(self.Gtk.SeparatorMenuItem())
        # Os perfis entram entre este separador e o de baixo: a lista muda quando
        # alguém cria ou apaga um perfil na interface.
        self.profile_base = len(self.menu.get_children())
        self.profile_end = self.Gtk.SeparatorMenuItem()
        self.menu.append(self.profile_end)
        self.profile_items = {}
        self.shown_profiles = ()
        self.shown_profile = ""
        # -----------------------------------------------------

        quit_item = self.Gtk.MenuItem(label="Sair")
        quit_item.connect("activate", lambda *_: self.send("quit"))
        quit_item.show()
        self.menu.append(quit_item)
        self.indicator.set_menu(self.menu)
        self.indicator.set_secondary_activate_target(self.open_item)

        self.GLib.timeout_add(POLL_MS, self.refresh)
        self.refresh()

    def icon_path(self, name: str) -> str:
        candidate = self.assets / f"{name}.png"
        return str(candidate) if candidate.exists() else ICON_FALLBACK

    def send(self, command: str, value: str | None = None) -> dict:
        try:
            payload = {"cmd": command}
            if value is not None:
                payload["value"] = value
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(1.5)
                client.connect(self.socket_path)
                client.sendall((json.dumps(payload) + "\n").encode())
                data = client.recv(65536)
            return json.loads(data.decode() or "{}")
        except (OSError, ValueError):
            return {}

    def _blink_busy(self) -> bool:
        if self.processing:
            self.busy_alt = not self.busy_alt
            icon = icon_name(True, False, processing=True, busy_alt=self.busy_alt)
            self.indicator.set_icon_full(self.icon_path(icon), "Transcrevendo…")
            self.last_state = f"processing:{icon}"
        return True

    def refresh(self) -> bool:
        state = self.send("state")
        if not state:
            # App encerrou: a bandeja não faz sentido sozinha.
            self.Gtk.main_quit()
            return False
        dictating = bool(state.get("dictating"))
        recording = bool(state.get("recording"))
        processing = str(state.get("state")) == "processing"
        self.processing = processing
        if processing:
            icon = icon_name(dictating, False, processing=True, busy_alt=self.busy_alt)
            tooltip = "Transcrevendo…"
        elif recording:
            self.blink = not self.blink
            icon, tooltip = icon_name(dictating, True, self.blink), "Gravando…"
        elif dictating:
            icon, tooltip = icon_name(True, False), "Ditado ativo"
        else:
            icon, tooltip = icon_name(False, False), "Ditado desativado"
        marker = f"{state.get('state')}:{icon}"
        if marker != self.last_state:
            self.last_state = marker
            self.indicator.set_icon_full(self.icon_path(icon), tooltip)
            self.toggle_item.set_label("Parar ditado" if dictating else "Iniciar ditado")
        self._sync_profiles(state.get("profiles") or (), str(state.get("profile") or ""))
        return True

    def _sync_profiles(self, profiles, current: str) -> None:
        """Acompanha a lista de perfis, que muda quando alguém edita na interface."""
        signature = profile_signature(profiles)
        if signature != self.shown_profiles:
            self.shown_profiles = signature
            for item in self.profile_items.values():
                self.menu.remove(item)
            self.profile_items.clear()
            for offset, (slug, name) in enumerate(signature):
                item = self.Gtk.MenuItem(label=name)
                item.connect("activate", lambda *_, s=slug: self.send("profile", s))
                item.show()
                self.menu.insert(item, self.profile_base + offset)
                self.profile_items[slug] = item
            self.shown_profile = ""  # a lista mudou: remarca o vigente
        self._sync_profile(current)

    def _sync_profile(self, current: str) -> None:
        """Marca no menu o perfil vigente (pode ter sido trocado na interface)."""
        if current == self.shown_profile:
            return
        self.shown_profile = current
        for slug, name in self.shown_profiles:
            item = self.profile_items.get(slug)
            if item is not None:
                item.set_label(profile_label(name, slug == current))


def main() -> int:
    if len(sys.argv) < 2:
        print("uso: tray_helper.py <socket> [pasta de ícones]", file=sys.stderr)
        return 2
    assets = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent / "assets"
    tray = Tray(sys.argv[1], assets)
    tray.Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
