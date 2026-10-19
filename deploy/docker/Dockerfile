# syntax=docker/dockerfile:1

# VB Typer 2.0 — API + interface web num contêiner só.
#
# A API já entrega o webapp na mesma origem, então não há proxy interno, CORS
# entre serviços nem build de front. O cliente desktop fica FORA da imagem: ele
# precisa de X11, microfone e do cursor local (ver AGENTS.md).

# ---------------------------------------------------------------- build ------
FROM python:3.12-slim AS build

# `uv` sai da imagem oficial (o binário é estático, não arrasta runtime Python).
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /uvx /usr/local/bin/

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app/backend

# As dependências vêm antes, sozinhas, para aproveitar o cache de camadas.
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --frozen --no-dev --no-editable --no-install-project

COPY backend/src ./src
RUN uv sync --frozen --no-dev --no-editable

# --------------------------------------------------------------- imagem ------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    VB_TYPER_HOST=0.0.0.0 \
    VB_TYPER_PORT=8765 \
    VB_TYPER_DATA_DIR=/data \
    VB_TYPER_CONFIG_DIR=/data/config \
    VB_TYPER_WEB_DIR=/app/web

# A escuta em 0.0.0.0 vale DENTRO do contêiner; a porta só é publicada pelo
# compose numa interface (ZeroTier). Ver o README desta pasta.

COPY --from=build /opt/venv /opt/venv
COPY web /app/web

# O volume nomeado herda o dono deste diretório na primeira criação.
RUN useradd --create-home --uid 10001 vbtyper \
    && mkdir -p /data \
    && chown vbtyper:vbtyper /data

USER vbtyper
WORKDIR /app

EXPOSE 8765

# `/api/v1/health` é a rota pública de saúde — não exige token.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/v1/health', timeout=4)"]

# As migrações do banco rodam sozinhas no start (vb_typer.main:create_app).
CMD ["vb-typer-api"]
