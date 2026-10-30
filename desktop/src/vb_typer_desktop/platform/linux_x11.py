"""Adaptador Linux/X11: atalho global, foco, geometria e digitação direta."""

from __future__ import annotations

import os
import sys
import threading
import time
from collections.abc import Callable

from vb_typer_desktop.geometry import Rect

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
MAX_PARENT_DEPTH = 64
# Teclas enviadas por ida ao servidor X. Uma a uma custava ~13 ms por
# caractere; em lotes de 16 o custo cai para ~1–2 ms e a inserção de um ditado
# longo deixa de ser o maior atraso do cliente.
KEY_BATCH = 16
CANCELLED_INSERTION = "Inserção cancelada; transcrição preservada na janela."

# Máscaras de modificador do X para os nomes que o backend usa.
COMBO_MASKS = {
    "ctrl": 0x0004,  # ControlMask
    "alt": 0x0008,  # Mod1Mask
    "shift": 0x0001,  # ShiftMask
    "super": 0x0040,  # Mod4Mask
}
# Keysyms das teclas especiais; letras, dígitos e F1–F12 saem do próprio nome.
COMBO_KEYSYMS = {
    "Tab": 0xFF09,
    "Space": 0x0020,
    "Enter": 0xFF0D,
    "Backspace": 0xFF08,
    "Delete": 0xFFFF,
    "Insert": 0xFF63,
    "Home": 0xFF50,
    "End": 0xFF57,
    "PageUp": 0xFF55,
    "PageDown": 0xFF56,
    "ArrowUp": 0xFF52,
    "ArrowDown": 0xFF54,
    "ArrowLeft": 0xFF51,
    "ArrowRight": 0xFF53,
    "Backquote": 0x0060,
    "Minus": 0x002D,
    "Equal": 0x003D,
    "BracketLeft": 0x005B,
    "BracketRight": 0x005D,
    "Backslash": 0x005C,
    "Semicolon": 0x003B,
    "Quote": 0x0027,
    "Comma": 0x002C,
    "Period": 0x002E,
    "Slash": 0x002F,
}


def combo_keysym(name: str) -> int:
    """Keysym de uma tecla da combinação; 0 quando o nome não é conhecido."""
    special = COMBO_KEYSYMS.get(name)
    if special is not None:
        return special
    if len(name) == 1 and name.isalpha():
        return ord(name.lower())
    if len(name) == 1 and name.isdigit():
        return ord(name)
    if name.startswith("F") and name[1:].isdigit():
        number = int(name[1:])
        if 1 <= number <= 12:
            return 0xFFBE + number - 1  # XK_F1..XK_F12
    return 0


class ComboUnavailable(RuntimeError):
    """O X não entregou as combinações (sessão ausente ou combinação ocupada)."""


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


def _toplevel(connection, window):
    """Sobe do widget em foco até a janela que o gerenciador de janelas controla."""
    root = connection.screen().root
    current = window
    for _ in range(MAX_PARENT_DEPTH):
        parent = current.query_tree().parent
        if parent is None or parent.id == root.id:
            return current
        current = parent
    return current


def _has_window_state(connection, window, name: str) -> bool:
    from Xlib import Xatom

    state = window.get_full_property(connection.intern_atom("_NET_WM_STATE"), Xatom.ATOM)
    if state is None or not state.value:
        return False
    return connection.intern_atom(name) in state.value


def _is_fullscreen(connection, window) -> bool:
    """O estado fica na janela do cliente, não na moldura do gerenciador."""
    if _has_window_state(connection, window, "_NET_WM_STATE_FULLSCREEN"):
        return True
    try:
        children = window.query_tree().children
    except Exception:
        return False
    return any(
        _has_window_state(connection, child, "_NET_WM_STATE_FULLSCREEN") for child in children
    )


def window_rect(window_id: int | None) -> Rect | None:
    """Área da janela de topo em coordenadas da raiz.

    Devolve ``None`` quando a janela sumiu ou está em tela cheia — nesse caso o
    indicador não deve aparecer por cima.
    """
    if window_id is None:
        return None
    try:
        from Xlib import display

        connection = display.Display()
        try:
            root = connection.screen().root
            toplevel = _toplevel(connection, connection.create_resource_object("window", window_id))
            if toplevel.id == root.id:
                return None
            if _is_fullscreen(connection, toplevel):
                return None
            geometry = toplevel.get_geometry()
            if not (geometry.width and geometry.height):
                return None
            x, y = int(geometry.x), int(geometry.y)
            if toplevel.query_tree().parent.id != root.id:
                # Sem gerenciador de janelas reparentando: traduz para a raiz.
                position = root.translate_coords(toplevel, 0, 0)
                x, y = int(position.x), int(position.y)
            return Rect(x, y, int(geometry.width), int(geometry.height))
        finally:
            connection.close()
    except Exception:
        return None


def screen_rect() -> Rect | None:
    """Área da tela em coordenadas da raiz (o desktop virtual inteiro)."""
    try:
        from Xlib import display

        connection = display.Display()
        try:
            geometry = connection.screen().root.get_geometry()
            if not (geometry.width and geometry.height):
                return None
            return Rect(int(geometry.x), int(geometry.y), int(geometry.width), int(geometry.height))
        finally:
            connection.close()
    except Exception:
        return None


def pointer_position() -> tuple[int, int] | None:
    """Posição do ponteiro em coordenadas da raiz."""
    try:
        from Xlib import display

        connection = display.Display()
        try:
            pointer = connection.screen().root.query_pointer()
            return int(pointer.root_x), int(pointer.root_y)
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


def type_strokes(
    strokes: list[tuple[int, bool, int | None]],
    *,
    press: Callable[[int], None],
    release: Callable[[int], None],
    sync: Callable[[], None],
    before_batch: Callable[[], None],
    check_focus: Callable[[], None],
    cancel: threading.Event | None = None,
    batch: int = KEY_BATCH,
    key_delay: float = 0.0,
) -> None:
    """Envia as teclas em lotes: uma ida ao servidor X por lote, não por tecla.

    Cada tecla custava duas chamadas a ``fake_input``, um ``sync()``, a leitura
    do foco e a consulta do ponteiro — ~13 ms medidos por caractere, ou 9,6 s
    num ditado de 1.280 caracteres. Aqui o ``sync()`` e as conferências valem
    por lote (``KEY_BATCH``), o que baixa o custo sem tirar o cancelamento
    (conferido a cada tecla) nem a checagem de foco.

    ``strokes`` traz ``(keycode, precisa_shift, keycode_do_shift)``.
    """
    size = max(1, int(batch))
    last = len(strokes) - 1
    for index, (keycode, needs_shift, shift_code) in enumerate(strokes):
        if cancel is not None and cancel.is_set():
            raise RuntimeError(CANCELLED_INSERTION)
        if index % size == 0:
            before_batch()
        shifted = bool(needs_shift and shift_code is not None)
        if shifted:
            press(shift_code)  # type: ignore[arg-type]
        try:
            press(keycode)
        finally:
            release(keycode)
            if shifted:
                release(shift_code)  # type: ignore[arg-type]
        if index % size == size - 1 or index == last:
            sync()
        if key_delay > 0:
            if cancel is not None:
                cancel.wait(key_delay)
            else:
                time.sleep(key_delay)
    check_focus()


def type_text(
    text: str,
    target_window: int | None,
    cancel: threading.Event | None = None,
    modifier_timeout: float = 5,
    key_delay: float = 0.0,
    batch: int = KEY_BATCH,
) -> None:
    """Digita no ponto do cursor da janela em foco usando XTEST, em ritmo de teclado.

    Caracteres que o layout atual produz usam o keycode real (com Shift quando
    preciso), sem ida e volta de mapeamento por caractere. Caracteres ausentes
    do layout são atribuídos de uma vez a keycodes livres; um único
    ``MappingNotify`` cobre todos eles.

    O envio sai em lotes (ver ``type_strokes``): ``batch`` teclas por ida ao
    servidor X. ``key_delay`` continua existindo para aplicativos que engasgam
    com rajada — é configuração (``typing_delay_ms``), não código.
    """
    cancel = cancel or threading.Event()
    if cancel.is_set():
        raise RuntimeError(CANCELLED_INSERTION)
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
                    raise RuntimeError(CANCELLED_INSERTION)
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

        strokes: list[tuple[int, bool, int | None]] = []
        for char in text:
            symbol = keysym(char)
            entry = keymap.get(symbol)
            if entry is None:
                strokes.append((spares[symbol], False, shift_code))
            else:
                keycode, needs_shift = entry
                strokes.append((keycode, needs_shift, shift_code))

        def before_batch() -> None:
            wait_modifiers()
            check_focus()

        type_strokes(
            strokes,
            press=lambda code: fake_input(connection, X.KeyPress, code),
            release=lambda code: fake_input(connection, X.KeyRelease, code),
            sync=connection.sync,
            before_batch=before_batch,
            check_focus=check_focus,
            cancel=cancel,
            batch=batch,
            key_delay=key_delay,
        )
    finally:
        try:
            for keycode, original in originals.items():
                connection.change_keyboard_mapping(keycode, [original])
            if originals:
                connection.sync()
        finally:
            connection.close()


class ComboWatcher:
    """Combinações de perfil por grab global (``XGrabKey``), em thread própria.

    Diferente do atalho de gravar — que só **olha** o teclado e por isso deixa a
    tecla chegar ao aplicativo —, aqui a combinação é tomada do sistema: sem o
    grab, ``Ctrl+Alt+Tab`` trocaria de aba no navegador além de mudar o perfil.
    O grab sai ao parar, e o X o libera sozinho se o processo cair.

    A thread usa ``select`` no descritor do X com prazo curto: parar é
    determinístico, sem depender de evento nenhum chegar.
    """

    def __init__(
        self,
        bindings: dict[str, tuple[tuple[str, ...], str]],
        on_action: Callable[[str], None],
        on_error: Callable[[str], None] | None = None,
        interval: float = 0.1,
    ) -> None:
        self.bindings = dict(bindings)
        self.on_action = on_action
        self.on_error = on_error
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running or not self.bindings:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="vb-typer-combos", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=1)
        self._thread = None

    def _fail(self, message: str) -> None:
        if self.on_error is not None:
            self.on_error(message)

    def _run(self) -> None:
        from Xlib import X, display
        from Xlib.error import XError

        try:
            connection = display.Display()
        except Exception as exc:  # sem DISPLAY, por exemplo
            self._fail(f"sessão gráfica indisponível ({exc})")
            return

        grabs: list[tuple[int, int]] = []
        actions: dict[tuple[int, int], str] = {}
        try:
            root = connection.screen().root
            for action, (modifiers, key) in self.bindings.items():
                keycode = connection.keysym_to_keycode(combo_keysym(key))
                if not keycode:
                    continue
                mask = 0
                for name in modifiers:
                    mask |= COMBO_MASKS.get(name, 0)
                if not mask:
                    continue
                # Cada combinação também precisa das variantes com CapsLock e
                # NumLock, senão o atalho morre quando um deles está ligado.
                for extra in (0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask):
                    root.grab_key(keycode, mask | extra, False, X.GrabModeAsync, X.GrabModeAsync)
                    grabs.append((keycode, mask | extra))
                    actions[(keycode, mask | extra)] = action
            connection.sync()
            if not grabs:
                self._fail("nenhuma combinação válida para registrar")
                return
            self._loop(connection, actions)
        except XError as exc:
            self._fail(f"combinação já em uso por outro programa ({exc})")
        except Exception as exc:  # pragma: no cover - erro inesperado do X
            self._fail(str(exc))
        finally:
            try:
                for keycode, mask in grabs:
                    root.ungrab_key(keycode, mask)
                connection.sync()
            except Exception:  # pragma: no cover - conexão já perdida
                pass
            connection.close()

    def _loop(self, connection, actions: dict[tuple[int, int], str]) -> None:
        import select

        from Xlib import X

        pressed: set[tuple[int, int]] = set()
        descriptor = connection.fileno()
        while not self._stop.is_set():
            readable, _, _ = select.select([descriptor], [], [], self.interval)
            if not readable:
                continue
            while connection.pending_events():
                event = connection.next_event()
                if event.type not in (X.KeyPress, X.KeyRelease):
                    continue
                # CapsLock/NumLock não mudam a combinação.
                state = event.state & ~(X.LockMask | X.Mod2Mask)
                key = (event.detail, state)
                if event.type == X.KeyPress:
                    if key in pressed:
                        continue  # auto-repeat: só um passo por aperto
                    pressed.add(key)
                    action = actions.get(key)
                    if action:
                        self.on_action(action)
                else:
                    pressed.discard(key)


class LinuxX11Platform:
    """Integrações do X11 (porte do app 1.x)."""

    name = "linux-x11"

    def __init__(self, batch: int = KEY_BATCH, key_delay: float = 0.0) -> None:
        # Ritmo da inserção; o daemon ajusta pelas preferências (desktop.json).
        self.batch = batch
        self.key_delay = key_delay

    def ensure_session(self) -> None:
        if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
            raise RuntimeError("Este cliente requer uma sessão X11; Wayland ainda não é suportado.")
        if not os.environ.get("DISPLAY"):
            raise RuntimeError("Não encontrei a sessão gráfica X11 (DISPLAY).")

    def configure_typing(self, batch: int, delay: float) -> None:
        self.batch = max(1, int(batch))
        self.key_delay = max(0.0, float(delay))

    def active_window(self) -> int | None:
        return read_active_window()

    def type_text(
        self, text: str, target: int | None, cancel: threading.Event | None = None
    ) -> None:
        type_text(text, target, cancel, key_delay=self.key_delay, batch=self.batch)

    def hotkey_watcher(self, on_change: Callable[[str, bool], None]) -> ModifierWatcher:
        return ModifierWatcher(modifier_groups(), on_change)

    def combo_watcher(
        self,
        bindings: dict[str, tuple[tuple[str, ...], str]],
        on_action: Callable[[str], None],
        on_error: Callable[[str], None] | None = None,
    ) -> ComboWatcher:
        return ComboWatcher(bindings, on_action, on_error)

    def window_rect(self, window: int | None) -> Rect | None:
        return window_rect(window)

    def screen_rect(self) -> Rect | None:
        return screen_rect()

    def pointer_position(self) -> tuple[int, int] | None:
        return pointer_position()
