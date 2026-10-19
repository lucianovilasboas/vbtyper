"""Adaptador Linux/X11: atalho global, foco de entrada e digitação direta."""

from __future__ import annotations

import os
import sys
import threading
import time
from collections.abc import Callable

# Keysyms (nomes fixos do X) das teclas que contam como Ctrl e como Super.
CTRL_KEYSYMS = (0xFFE3, 0xFFE4)  # Control_L, Control_R
SUPER_KEYSYMS = (
    0xFFE7,
    0xFFE8,  # Meta_L, Meta_R
    0xFFEB,
    0xFFEC,  # Super_L, Super_R
    0xFFED,
    0xFFEE,  # Hyper_L, Hyper_R
)


def read_active_window() -> int | None:
    """Captura o foco de entrada X (inclusive janelas filhas), não o app do topo."""
    try:
        from Xlib import display

        connection = display.Display()
        try:
            focus = connection.get_input_focus().focus
            return getattr(focus, "id", None)
        finally:
            connection.close()
    except Exception:
        return None


def modifier_groups() -> dict[int, str]:
    """Keycodes que representam ``ctrl`` e ``super`` no layout atual."""
    from Xlib import display

    connection = display.Display()
    try:
        info = connection.display.info
        first = info.min_keycode
        count = info.max_keycode - info.min_keycode + 1
        mapping = connection.get_keyboard_mapping(first, count)
    finally:
        connection.close()
    wanted = {symbol: "ctrl" for symbol in CTRL_KEYSYMS}
    wanted.update({symbol: "super" for symbol in SUPER_KEYSYMS})
    groups: dict[int, str] = {}
    for index, row in enumerate(mapping):
        for symbol in row[:2]:
            group = wanted.get(int(symbol))
            if group is not None:
                groups.setdefault(first + index, group)
                break
    return groups


class _KeymapReader:
    """Leitor do mapa de teclas; a conexão X pertence a quem o usa."""

    def __init__(self) -> None:
        from Xlib import display

        self._connection = display.Display()

    def __call__(self) -> bytes:
        return self._connection.query_keymap()

    def close(self) -> None:
        self._connection.close()


class ModifierWatcher:
    """Observa Ctrl/Super consultando o estado do teclado (``XQueryKeymap``).

    O listener de eventos do XRecord (``pynput``) não encerra de forma confiável:
    ``stop()`` retorna, mas a thread de escuta continua viva, e cada pausa
    deixaria um contexto X pendurado. Consultar o estado dos modificadores a
    cada quadro é determinístico, para na hora e basta para um atalho de segurar.
    """

    def __init__(
        self,
        groups: dict[int, str],
        on_change: Callable[[str, bool], None],
        interval: float = 0.025,
        reader_factory: Callable[[], Callable[[], bytes]] | None = None,
    ) -> None:
        self.groups = dict(groups)
        self.on_change = on_change
        self.interval = interval
        # A fábrica abre a conexão X na thread que observa e devolve o leitor.
        self._reader_factory = reader_factory or _KeymapReader
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._pressed: set[str] = set()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="vb-typer-hotkey", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=1)
        self._thread = None

    def apply(self, bitmap: bytes) -> None:
        """Compara com o estado anterior e avisa cada transição em ordem estável."""
        held: dict[str, bool] = {}
        for keycode, group in self.groups.items():
            index, bit = keycode // 8, keycode % 8
            if index < len(bitmap) and bitmap[index] & (1 << bit):
                held.setdefault(group, True)
        for group in held:
            if group not in self._pressed:
                self._pressed.add(group)
                self.on_change(group, True)
        for group in list(self._pressed):
            if group not in held:
                self._pressed.discard(group)
                self.on_change(group, False)

    def _run(self) -> None:
        try:
            reader = self._reader_factory()
        except Exception as exc:
            print(f"Atalho global indisponível: {exc}", file=sys.stderr, flush=True)
            return
        close = getattr(reader, "close", None)
        try:
            while not self._stop.is_set():
                try:
                    bitmap = reader()
                except Exception as exc:
                    # Sem conexão X não há atalho; avisa uma vez e encerra a observação.
                    print(f"Atalho global interrompido: {exc}", file=sys.stderr, flush=True)
                    return
                if bitmap:
                    self.apply(bitmap)
                self._stop.wait(self.interval)
        finally:
            if close is not None:
                close()


def type_text(
    text: str,
    target_window: int | None,
    cancel: threading.Event | None = None,
    modifier_timeout: float = 5,
    key_delay: float = 0.004,
) -> None:
    """Digita no ponto do cursor da janela em foco usando XTEST, em ritmo de teclado.

    Caracteres que o layout atual produz usam o keycode real (com Shift quando
    preciso), sem ida e volta de mapeamento por caractere. Caracteres ausentes
    do layout são atribuídos de uma vez a keycodes livres; um único
    ``MappingNotify`` cobre todos eles.
    """
    cancel = cancel or threading.Event()
    if cancel.is_set():
        raise RuntimeError("Inserção cancelada; transcrição preservada na janela.")
    if target_window is None or read_active_window() != target_window:
        raise RuntimeError("O foco mudou; transcrição preservada na janela, sem inserção.")
    from Xlib import X, display
    from Xlib.ext.xtest import fake_input

    connection = display.Display()
    deadline = time.monotonic() + modifier_timeout
    held_mask = X.ShiftMask | X.ControlMask | X.Mod1Mask | X.Mod4Mask | X.Mod5Mask
    spares: dict[int, int] = {}
    originals: dict[int, tuple[int, ...]] = {}
    try:
        info = connection.display.info
        first, count = info.min_keycode, info.max_keycode - info.min_keycode + 1
        mapping = connection.get_keyboard_mapping(first, count)
        keymap: dict[int, tuple[int, bool]] = {}
        free_rows: list[int] = []
        for index, row in enumerate(mapping):
            keycode = first + index
            if not any(row):
                free_rows.append(keycode)
            for level, symbol in enumerate(row[:2]):
                if symbol and symbol not in keymap:
                    keymap[int(symbol)] = (keycode, level == 1)
        shift_code = keymap.get(0xFFE1, (None, False))[0] or keymap.get(0xFFE2, (None, False))[0]

        def keysym(char: str) -> int:
            if char == "\n":
                return 0xFF0D
            if char == "\t":
                return 0xFF09
            code = ord(char)
            return code if code < 256 else 0x01000000 | code

        def wait_modifiers() -> None:
            while True:
                if cancel.is_set():
                    raise RuntimeError("Inserção cancelada; transcrição preservada na janela.")
                if not (connection.screen().root.query_pointer().mask & held_mask):
                    return
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "Solte as teclas modificadoras. Transcrição preservada na janela."
                    )
                cancel.wait(0.005)

        def check_focus() -> None:
            focus = connection.get_input_focus().focus
            if getattr(focus, "id", None) != target_window:
                raise RuntimeError(
                    "O foco mudou; inserção interrompida. Texto preservado na janela."
                )

        # Uma única mudança de mapeamento para todos os caracteres que o layout não produz.
        missing = []
        for char in text:
            symbol = keysym(char)
            if symbol not in keymap and symbol not in missing:
                missing.append(symbol)
        if len(missing) > len(free_rows):
            raise RuntimeError("Sem teclas X11 livres para digitação Unicode.")
        for symbol, keycode in zip(missing, free_rows, strict=False):
            index = keycode - first
            originals[keycode] = tuple(mapping[index])
            connection.change_keyboard_mapping(keycode, [(symbol,) * len(mapping[index])])
            spares[symbol] = keycode
        if spares:
            connection.sync()
            # Os clientes precisam processar o MappingNotify antes dessas teclas.
            cancel.wait(0.06)

        for char in text:
            if cancel.is_set():
                raise RuntimeError("Inserção cancelada; transcrição preservada na janela.")
            symbol = keysym(char)
            entry = keymap.get(symbol)
            if entry is None:
                keycode, needs_shift = spares[symbol], False
            else:
                keycode, needs_shift = entry
            wait_modifiers()
            check_focus()
            if needs_shift and shift_code:
                fake_input(connection, X.KeyPress, shift_code)
            try:
                fake_input(connection, X.KeyPress, keycode)
            finally:
                fake_input(connection, X.KeyRelease, keycode)
                if needs_shift and shift_code:
                    fake_input(connection, X.KeyRelease, shift_code)
            connection.sync()
            if key_delay:
                cancel.wait(key_delay)
        check_focus()
    finally:
        try:
            for keycode, original in originals.items():
                connection.change_keyboard_mapping(keycode, [original])
            if originals:
                connection.sync()
        finally:
            connection.close()


class LinuxX11Platform:
    """Integrações do X11 (porte do app 1.x)."""

    name = "linux-x11"

    def ensure_session(self) -> None:
        if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
            raise RuntimeError("Este cliente requer uma sessão X11; Wayland ainda não é suportado.")
        if not os.environ.get("DISPLAY"):
            raise RuntimeError("Não encontrei a sessão gráfica X11 (DISPLAY).")

    def active_window(self) -> int | None:
        return read_active_window()

    def type_text(
        self, text: str, target: int | None, cancel: threading.Event | None = None
    ) -> None:
        type_text(text, target, cancel)

    def hotkey_watcher(self, on_change: Callable[[str, bool], None]) -> ModifierWatcher:
        return ModifierWatcher(modifier_groups(), on_change)
