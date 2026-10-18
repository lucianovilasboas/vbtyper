"""Segredos e checagens de segurança do servidor local."""

from __future__ import annotations

import contextlib
import os
import secrets
from urllib.parse import urlsplit

from vb_typer.core.config import AppSettings
from vb_typer.core.paths import AppPaths

TOKEN_COOKIE = "vb_typer_token"


def load_or_create_token(paths: AppPaths, override: str | None = None) -> str:
    """Devolve o token da API, criando um arquivo ``0600`` na primeira execução."""
    if override:
        return override
    if paths.token_file.is_file():
        token = paths.token_file.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(32)
    paths.token_file.parent.mkdir(parents=True, exist_ok=True)
    paths.token_file.write_text(token + "\n", encoding="utf-8")
    with contextlib.suppress(OSError):
        os.chmod(paths.token_file, 0o600)
    return token


def token_matches(provided: str | None, expected: str) -> bool:
    if not provided:
        return False
    return secrets.compare_digest(provided, expected)


def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def _host_without_port(host_header: str) -> str:
    value = host_header.strip().lower()
    if value.startswith("["):  # IPv6: [::1]:8765
        end = value.find("]")
        return value[1:end] if end != -1 else value
    return value.rsplit(":", 1)[0] if ":" in value else value


def host_allowed(host_header: str | None, settings: AppSettings) -> bool:
    if not host_header:
        return False
    host = _host_without_port(host_header)
    allowed = {item.lower() for item in settings.allowed_hosts}
    allowed.update({"127.0.0.1", "localhost", "::1"})
    return host in allowed


def allowed_origins(settings: AppSettings) -> set[str]:
    base = {
        f"http://127.0.0.1:{settings.port}",
        f"http://localhost:{settings.port}",
        f"http://[::1]:{settings.port}",
    }
    base.update(origin.rstrip("/") for origin in settings.cors_origins)
    return base


def origin_allowed(origin: str | None, settings: AppSettings) -> bool:
    """Sem ``Origin`` (clientes nativos e curl) a requisição é aceita.

    Navegadores sempre enviam ``Origin`` em requisições cross-origin e em
    chamadas ``fetch`` não-GET, o que bloqueia CSRF/DNS-rebinding.
    """
    if not origin:
        return True
    return origin.rstrip("/") in allowed_origins(settings)


def origin_of(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}".lower()
