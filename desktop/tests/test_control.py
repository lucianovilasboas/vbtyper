"""Canal de controle local: um JSON por linha no socket Unix."""

from __future__ import annotations

from vb_typer_desktop.control import ControlServer, control_socket_path, talk_to_running_instance


def test_round_trip_answers_the_state():
    server = ControlServer(
        control_socket_path(), lambda cmd, value=None: {"ok": True, "cmd": cmd, "value": value}
    )
    server.start()
    try:
        assert talk_to_running_instance("state") == {"ok": True, "cmd": "state", "value": None}
    finally:
        server.stop()


def test_unknown_command_replies_not_ok():
    server = ControlServer(control_socket_path(), lambda cmd, value=None: {"ok": False})
    server.start()
    try:
        assert talk_to_running_instance("nada") == {"ok": False}
    finally:
        server.stop()


def test_nothing_listening_returns_none():
    assert talk_to_running_instance("state") is None


def test_stop_removes_the_socket():
    path = control_socket_path()
    server = ControlServer(path, lambda cmd, value=None: {"ok": True})
    server.start()
    assert path.exists()
    server.stop()
    assert not path.exists()


def test_socket_name_differs_from_the_1x_app():
    # O app 1.x usa ``vb-typer-<uid>.sock``; as duas instâncias rodam em paralelo.
    assert "desktop" in control_socket_path().name


def test_value_travels_with_the_command():
    """A bandeja manda o perfil escolhido junto do comando."""
    seen: list[tuple[str, object]] = []

    def handler(command: str, value=None):
        seen.append((command, value))
        return {"ok": True}

    server = ControlServer(control_socket_path(), handler)
    server.start()
    try:
        import json
        import socket

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(2)
            client.connect(str(control_socket_path()))
            client.sendall((json.dumps({"cmd": "profile", "value": "email"}) + "\n").encode())
            client.recv(65536)
    finally:
        server.stop()
    assert seen == [("profile", "email")]
