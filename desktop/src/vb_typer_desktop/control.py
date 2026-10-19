"""Canal de controle local (socket Unix) usado pela bandeja."""

from __future__ import annotations

import contextlib
import json
import os
import socket
import threading
from pathlib import Path

# Nome próprio: o app 1.x usa ``vb-typer-<uid>.sock`` e continua rodando em
# paralelo, então as duas instâncias nunca podem disputar o mesmo socket.
SOCKET_BASENAME = "vb-typer-desktop"


def control_socket_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    return Path(runtime) / f"{SOCKET_BASENAME}-{os.getuid()}.sock"


def talk_to_running_instance(command: str) -> dict | None:
    """Resposta da instância em execução, ou ``None`` quando ninguém escuta."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(1.0)
            client.connect(str(control_socket_path()))
            client.sendall((json.dumps({"cmd": command}) + "\n").encode())
            data = client.recv(4096)
    except (OSError, ValueError):
        return None
    if not data:
        return None
    try:
        return json.loads(data.decode() or "{}")
    except ValueError:
        return None


class ControlServer:
    """Servidor de controle: um JSON por linha, na thread do socket."""

    def __init__(self, path: Path, handler) -> None:
        self.path = path
        self.handler = handler
        self.socket: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.stopped = threading.Event()

    def start(self) -> None:
        self.path.unlink(missing_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self.path))
        with contextlib.suppress(OSError):
            os.chmod(self.path, 0o600)
        server.listen(4)
        server.settimeout(0.5)
        self.socket = server
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        while not self.stopped.is_set():
            try:
                connection, _ = self.socket.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            with connection:
                try:
                    connection.settimeout(1.5)
                    raw = connection.recv(1024).decode("utf-8", "replace").strip()
                    request = json.loads(raw or "{}")
                    reply = self.handler(str(request.get("cmd", "")))
                except (OSError, ValueError):
                    reply = {"ok": False}
                with contextlib.suppress(OSError):
                    connection.sendall(json.dumps(reply).encode())

    def stop(self) -> None:
        self.stopped.set()
        if self.socket is not None:
            self.socket.close()
            self.socket = None
        self.path.unlink(missing_ok=True)
