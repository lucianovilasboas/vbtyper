"""CLI do cliente desktop: ditado por atalho global consumindo a API local."""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import replace

from vb_typer_desktop import __version__, preferences
from vb_typer_desktop.api import DEFAULT_BASE_URL, ApiClient, ApiError, load_token
from vb_typer_desktop.control import ControlServer, control_socket_path, talk_to_running_instance
from vb_typer_desktop.daemon import Daemon
from vb_typer_desktop.notify import notify
from vb_typer_desktop.platform import get_platform
from vb_typer_desktop.tray import start_indicator, start_tray
from vb_typer_desktop.ui import ui_url

BACKEND_HINT = "Inicie o serviço com: systemctl --user start vb-typer-api"


def _warn_if_backend_down(api: ApiClient, attempts: int = 10, delay: float = 0.5) -> None:
    """Avisa cedo quando a API ou a chave não estão prontas, sem impedir o ditado."""
    for _ in range(attempts):
        try:
            ready = api.ready()
        except ApiError:
            time.sleep(delay)
            continue
        if not ready.get("api_key_configured"):
            notify(
                "VB Typer — erro",
                "Chave OpenAI ausente. Salve na interface ou rode: vb-typer-api --setup",
                "critical",
                sound=False,
            )
        return
    notify("VB Typer — erro", f"A API do VB Typer não respondeu. {BACKEND_HINT}", "critical")


def _status(api: ApiClient, current: preferences.Preferences) -> int:
    print(f"VB Typer Desktop {__version__}")
    print(f"API: {api.base_url}")
    print(f"Token encontrado: {'sim' if load_token() else 'não'}")
    print(f"Preferências: {preferences.preference_file()}")
    print(
        f"Avisos: {current.notices} · âncora: {current.anchor}/{current.position} "
        f"· som: {'sim' if current.sound else 'não'} · tamanho: {current.size}"
    )
    print(f"Reação: velocidade {current.speed:g} · sensibilidade {current.sensitivity:g}")
    print(f"Desenho da gravação: {current.shape}")
    try:
        ready = api.ready()
    except ApiError as exc:
        print(f"API indisponível: {exc} ({BACKEND_HINT})", file=sys.stderr)
        return 1
    print(f"Estado: {ready.get('status')}")
    print(f"Banco: {ready.get('database')}")
    print(f"Chave OpenAI configurada: {'sim' if ready.get('api_key_configured') else 'não'}")
    print(f"Socket de controle: {control_socket_path()}")
    return 0


def _self_test(api: ApiClient) -> int:
    """Confere o ambiente local; não grava áudio nem chama a OpenAI."""
    failed = False
    try:
        get_platform().ensure_session()
    except RuntimeError as exc:
        print(f"Sessão gráfica: falhou — {exc}", file=sys.stderr)
        failed = True
    else:
        print("Sessão gráfica X11: ok")
    if shutil.which("arecord"):
        print("Gravador arecord: ok")
    else:
        print("Gravador arecord: ausente", file=sys.stderr)
        failed = True
    try:
        ready = api.ready()
    except ApiError as exc:
        print(f"API: falhou — {exc} ({BACKEND_HINT})", file=sys.stderr)
        failed = True
    else:
        print(
            f"API: {ready.get('status')} · banco={ready.get('database')} "
            f"· chave={ready.get('api_key_configured')}"
        )
    print(f"Socket de controle: {control_socket_path()}")
    return 1 if failed else 0


def _teardown(daemon: Daemon, server: ControlServer, helpers: list, api: ApiClient) -> None:
    daemon.shutdown()
    server.stop()
    for process in helpers:
        if process.poll() is None:
            process.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                process.wait(timeout=3)
    api.close()


def _install_stop_handlers(daemon: Daemon) -> None:
    """Encerra pelo caminho normal em SIGTERM/SIGINT.

    Sem isto, um ``systemctl --user restart`` mata o processo na hora e deixa a
    bandeja e o indicador para trás (eles só sairiam sozinhos ao perceber o
    socket morto). O handler apenas sinaliza; quem desmonta é o fluxo normal.
    """

    def request_stop(signum, frame) -> None:
        daemon.done.set()

    for name in ("SIGTERM", "SIGINT"):
        with contextlib.suppress(ValueError, OSError):
            signal.signal(getattr(signal, name), request_stop)


def run_daemon(
    api: ApiClient, with_tray: bool, open_browser: bool, prefs: preferences.Preferences
) -> int:
    _warn_if_backend_down(api)
    daemon = Daemon(
        api,
        notify_fn=lambda title, message, urgency="normal": notify(
            title, message, urgency, sound=prefs.sound
        ),
        preferences=prefs,
    )
    socket_path = control_socket_path()
    server = ControlServer(socket_path, daemon.control_command)
    server.start()
    helpers = []
    if with_tray:
        tray_process = start_tray(socket_path)
        if tray_process is not None:
            helpers.append(tray_process)
    if prefs.shows_indicator:
        indicator_process = start_indicator(
            socket_path,
            speed=prefs.speed,
            sensitivity=prefs.sensitivity,
            shape=prefs.shape,
        )
        if indicator_process is not None:
            helpers.append(indicator_process)
    try:
        daemon.start_listener()
    except RuntimeError as exc:
        notify("VB Typer — erro", str(exc), "critical")
        print(f"Falha ao iniciar o ditado: {exc}", file=sys.stderr)
        _teardown(daemon, server, helpers, api)
        return 1
    if open_browser:
        daemon.show_ui()
    print(
        f"VB Typer ativo (Ctrl+Super para falar). Avisos: {prefs.notices}. "
        f"Interface em {ui_url(api.base_url)}",
        flush=True,
    )
    _install_stop_handlers(daemon)
    try:
        daemon.wait()
    except KeyboardInterrupt:
        pass
    finally:
        _teardown(daemon, server, helpers, api)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vb-typer-desktop", description="Ditado por voz por atalho global (Ctrl+Super)."
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("VB_TYPER_API_BASE_URL") or DEFAULT_BASE_URL,
        help="endereço da API (padrão: VB_TYPER_API_BASE_URL ou a API local)",
    )
    parser.add_argument("--status", action="store_true", help="mostrar o estado e sair")
    parser.add_argument("--self-test", action="store_true", help="verificar o ambiente sem ditar")
    parser.add_argument("--ui", action="store_true", help="abrir a interface ao iniciar")
    parser.add_argument("--no-tray", action="store_true", help="não usar a bandeja do sistema")
    parser.add_argument("--force", action="store_true", help="ignorar instância já em execução")
    parser.add_argument("--version", action="store_true", help="mostrar a versão e sair")
    parser.add_argument(
        "--notices",
        choices=preferences.NOTICE_MODES,
        default=None,
        help="como avisar: indicator (padrão), balloons (comportamento antigo), both, none",
    )
    parser.add_argument(
        "--write-preferences",
        action="store_true",
        help="gravar o arquivo de preferências com os valores atuais e sair",
    )
    args = parser.parse_args(argv)

    if args.version:
        print(f"VB Typer Desktop {__version__}")
        return 0

    prefs = preferences.load()
    if args.notices:
        prefs = replace(prefs, notices=args.notices)
    if args.write_preferences:
        print(f"Preferências gravadas em {preferences.save(prefs)}")
        return 0

    api = ApiClient(base_url=args.base_url)
    if args.status:
        code = _status(api, prefs)
        api.close()
        return code
    if args.self_test:
        code = _self_test(api)
        api.close()
        return code

    # Uma segunda instância criaria um segundo listener: o mesmo Ctrl+Super
    # gravaria duas vezes e o texto sairia duplicado/intercalado no campo.
    if not args.force and talk_to_running_instance("show") is not None:
        notify("VB Typer", "O VB Typer já está em execução; interface existente aberta.")
        print("VB Typer já está em execução.", flush=True)
        api.close()
        return 0

    return run_daemon(api, with_tray=not args.no_tray, open_browser=args.ui, prefs=prefs)


if __name__ == "__main__":
    raise SystemExit(main())
