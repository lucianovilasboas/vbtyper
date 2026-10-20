"""Interface web servida pelo backend, na mesma origem."""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from tests.conftest import TEST_TOKEN
from vb_typer.core.config import AppSettings
from vb_typer.core.security import TOKEN_COOKIE
from vb_typer.main import create_app


@pytest.fixture
def web_dir(tmp_path):
    root = tmp_path / "web"
    (root / "static").mkdir(parents=True)
    (root / "index.html").write_text("<!doctype html><title>VB Typer</title>", encoding="utf-8")
    (root / "static" / "app.js").write_text("console.log('ok')", encoding="utf-8")
    return root


@pytest.fixture
def web_settings(tmp_path, monkeypatch, web_dir) -> AppSettings:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return AppSettings(
        config_dir=tmp_path / "cfg",
        data_dir=tmp_path / "data",
        api_token=TEST_TOKEN,
        allowed_hosts=("testserver", "127.0.0.1", "localhost"),
        worker_concurrency=1,
        log_level="WARNING",
        web_dir=web_dir,
    )


@pytest_asyncio.fixture
async def web_client(web_settings):
    application = create_app(web_settings)
    async with LifespanManager(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


async def test_root_serves_html_and_sets_httponly_cookie(web_client):
    response = await web_client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "VB Typer" in response.text
    cookie = response.headers["set-cookie"].lower()
    assert TOKEN_COOKIE in cookie
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "secure" not in cookie


async def test_secure_cookie_when_configured(web_settings):
    """Atrás de TLS (Traefik), o cookie de sessão ganha o atributo Secure."""
    settings = web_settings.model_copy(update={"cookie_secure": True})
    application = create_app(settings)
    async with LifespanManager(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
            response = await client.get("/")
    assert "secure" in response.headers["set-cookie"].lower()


async def test_static_assets_are_served(web_client):
    response = await web_client.get("/static/app.js")
    assert response.status_code == 200
    assert "console.log" in response.text


async def test_cookie_authenticates_api_requests(web_client):
    await web_client.get("/")  # estabelece o cookie no cliente
    response = await web_client.get("/api/v1/settings")
    assert response.status_code == 200
    assert response.json()["model"]


async def test_api_still_requires_credentials_without_cookie(web_client):
    response = await web_client.get("/api/v1/settings")
    assert response.status_code == 401
