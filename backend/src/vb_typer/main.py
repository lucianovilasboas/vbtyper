"""Aplicação FastAPI: composição, middleware, erros e ciclo de vida."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from vb_typer import __version__
from vb_typer.api.deps import build_container
from vb_typer.api.v1.router import api_router
from vb_typer.core.config import AppSettings, get_settings
from vb_typer.core.logging import configure_logging
from vb_typer.core.paths import AppPaths, ensure_paths, resolve_paths, secure_file
from vb_typer.core.security import (
    TOKEN_COOKIE,
    allowed_origins,
    host_allowed,
    load_or_create_token,
    origin_allowed,
)
from vb_typer.db import migrate
from vb_typer.domain.errors import DomainError
from vb_typer.workers.manager import JobManager

logger = logging.getLogger("vb_typer.api")

DESCRIPTION = """
API REST local do VB Typer.

O backend é o único dono do histórico, dos áudios e da credencial OpenAI.
Clientes desktop e web consomem estas rotas e nunca falam direto com o provedor
nem leem o banco. Por padrão escuta apenas em `127.0.0.1` e exige um token
Bearer (gerado em `api-token` no diretório de configuração).
"""


def _error_response(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    container = app.state.container
    manager = JobManager(
        container.transcription, container.openai, container.settings, container.profiles
    )
    app.state.manager = manager
    await manager.start()
    logger.info(
        "API pronta em http://%s:%s (docs em /docs)",
        container.settings.host,
        container.settings.port,
    )
    try:
        yield
    finally:
        await manager.stop()
        await container.openai.aclose()
        container.engine.dispose()


def create_app(settings: AppSettings | None = None, paths: AppPaths | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    resolved = ensure_paths(paths or resolve_paths(settings))
    migrate.upgrade(resolved.database)
    secure_file(resolved.database)
    token = load_or_create_token(resolved, settings.api_token)
    container = build_container(settings, resolved)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=DESCRIPTION,
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
        lifespan=_lifespan,
    )
    app.state.container = container
    app.state.api_token = token
    app.state.manager = None

    _install_middleware(app, container)
    _install_error_handlers(app)
    app.include_router(api_router)
    _mount_web_ui(app, settings, token)

    return app


def web_directory(settings: AppSettings) -> Path | None:
    """Diretório da interface web, quando existir."""
    if not settings.serve_web_ui:
        return None
    candidate = settings.web_dir or (Path(__file__).resolve().parents[3] / "web")
    candidate = Path(candidate)
    return candidate if (candidate / "index.html").is_file() else None


def _mount_web_ui(app: FastAPI, settings: AppSettings, token: str) -> None:
    web_dir = web_directory(settings)
    if web_dir is None:

        @app.get("/", include_in_schema=False)
        def index() -> dict:
            return {
                "app": settings.app_name,
                "version": __version__,
                "docs": "/docs",
                "openapi": "/api/v1/openapi.json",
            }

        return

    static_dir = web_dir / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=static_dir), name="web-static")

    index_html = (web_dir / "index.html").read_text(encoding="utf-8")

    @app.get("/", include_in_schema=False, response_class=HTMLResponse)
    def web_index() -> HTMLResponse:
        # O app web roda na mesma origem: o token vai num cookie HttpOnly e
        # SameSite=Strict, então o JavaScript nunca o manuseia.
        response = HTMLResponse(index_html)
        response.set_cookie(
            TOKEN_COOKIE,
            token,
            httponly=True,
            samesite="strict",
            secure=settings.cookie_secure,
            path="/",
        )
        return response

    # O service worker precisa morar na raiz para controlar "/": servido em
    # /static ele só controlaria /static. O manifest pode ficar em qualquer
    # caminho, mas a raiz deixa a URL curta e estável.
    @app.get("/sw.js", include_in_schema=False)
    def service_worker() -> FileResponse:
        return FileResponse(
            web_dir / "static" / "sw.js",
            media_type="application/javascript",
            headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
        )

    @app.get("/manifest.webmanifest", include_in_schema=False)
    def web_manifest() -> FileResponse:
        return FileResponse(
            web_dir / "static" / "manifest.webmanifest",
            media_type="application/manifest+json",
            headers={"Cache-Control": "no-cache"},
        )

    logger.info("Interface web servida de %s", web_dir)


def _install_middleware(app: FastAPI, container) -> None:
    settings = container.settings

    @app.middleware("http")
    async def enforce_local_only(request: Request, call_next):
        if not host_allowed(request.headers.get("host"), settings):
            return _error_response(request, 400, "invalid_host", "Host não permitido.")
        if settings.trust_origin_header and not origin_allowed(
            request.headers.get("origin"), settings
        ):
            return _error_response(request, 403, "invalid_origin", "Origem não permitida.")
        return await call_next(request)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "Falha não tratada %s %s [%s]",
                request.method,
                request.url.path,
                request.state.request_id,
            )
            raise
        elapsed_ms = int((time.monotonic() - started) * 1000)
        response.headers["X-Request-ID"] = request.state.request_id
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            # App local: o navegador sempre revalida os assets da interface.
            response.headers["Cache-Control"] = "no-cache"
        logger.info(
            "%s %s -> %s (%d ms) [%s]",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request.state.request_id,
        )
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(allowed_origins(settings)),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Request-ID"],
    )


def _install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return _error_response(request, exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        if errors:
            first = errors[0]
            location = ".".join(str(part) for part in first.get("loc", ()) if part != "body")
            message = first.get("msg", "Requisição inválida.")
            message = f"{location}: {message}" if location else message
        else:
            message = "Requisição inválida."
        return _error_response(request, 422, "validation_error", message)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error_response(request, exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Erro interno não tratado [%s]", request.state.request_id)
        return _error_response(request, 500, "internal_error", "Erro interno do servidor.")
