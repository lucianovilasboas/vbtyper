"""CLI do backend: iniciar o servidor e administrar a credencial."""

from __future__ import annotations

import argparse
import getpass
import sys

from vb_typer import __version__
from vb_typer.core.config import AppSettings, get_settings
from vb_typer.core.logging import configure_logging
from vb_typer.core.paths import ensure_paths, resolve_paths
from vb_typer.core.security import load_or_create_token


def _setup_key(settings: AppSettings) -> int:
    from vb_typer.adapters.secrets import SecretsAdapter

    try:
        key = getpass.getpass("Chave da API OpenAI (não será exibida): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelado.", file=sys.stderr)
        return 1
    if not key:
        print("Nenhuma chave informada.", file=sys.stderr)
        return 1
    try:
        SecretsAdapter(settings).store_api_key(key)
    except Exception as exc:  # pragma: no cover - depende do ambiente gráfico
        print(f"Falha ao salvar no cofre: {exc}", file=sys.stderr)
        return 1
    print("Chave salva no cofre do sistema.")
    return 0


def _status(settings: AppSettings) -> int:
    from vb_typer.adapters.secrets import SecretsAdapter

    paths = ensure_paths(resolve_paths(settings))
    print(f"VB Typer API {__version__}")
    print(f"Banco de dados: {paths.database}")
    print(f"Áudios: {paths.audio_dir}")
    print(f"Arquivo de token: {paths.token_file}")
    try:
        configured = SecretsAdapter(settings).has_api_key()
        print(f"Chave OpenAI configurada: {'sim' if configured else 'não'}")
    except Exception as exc:  # pragma: no cover
        print(f"Cofre indisponível: {exc}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vb-typer-api", description="API REST local do VB Typer.")
    parser.add_argument("--host", default=None, help="endereço de escuta (padrão: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="porta (padrão: 8765)")
    parser.add_argument("--reload", action="store_true", help="recarregar ao editar o código")
    parser.add_argument("--log-level", default=None, help="DEBUG, INFO, WARNING, ERROR")
    parser.add_argument("--setup", action="store_true", help="salvar a chave OpenAI no cofre")
    parser.add_argument(
        "--status", action="store_true", help="mostrar o estado sem revelar segredos"
    )
    parser.add_argument(
        "--print-token", action="store_true", help="imprimir o token de acesso (sensível)"
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.setup:
        return _setup_key(settings)
    if args.status:
        return _status(settings)
    if args.print_token:
        paths = ensure_paths(resolve_paths(settings))
        print(load_or_create_token(paths, settings.api_token))
        return 0

    import uvicorn

    host = args.host or settings.host
    port = args.port or settings.port
    log_level = (args.log_level or settings.log_level).lower()
    configure_logging(settings.log_level)
    uvicorn.run(
        "vb_typer.main:create_app",
        factory=True,
        host=host,
        port=port,
        log_level=log_level,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
