"""Fixtures compartilhadas dos testes."""

from __future__ import annotations

import asyncio
import io
import time
import wave

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from vb_typer.core.config import AppSettings
from vb_typer.main import create_app

TEST_TOKEN = "token-de-teste"
OPENAI_HOST = "https://api.openai.com/v1"


@pytest.fixture(autouse=True)
def isolate_keyring(monkeypatch):
    """Impede que os testes leiam/gravem no cofre real do sistema."""
    import keyring

    store: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(keyring, "get_password", lambda service, user: store.get((service, user)))

    def setter(service, user, value, _store=store):
        _store[(service, user)] = value

    monkeypatch.setattr(keyring, "set_password", setter)
    return store


@pytest.fixture
def app_settings(tmp_path, monkeypatch) -> AppSettings:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return AppSettings(
        config_dir=tmp_path / "cfg",
        data_dir=tmp_path / "data",
        api_token=TEST_TOKEN,
        allowed_hosts=("testserver", "127.0.0.1", "localhost"),
        worker_concurrency=1,
        log_level="WARNING",
        web_dir=tmp_path / "sem-interface-web",
    )


@pytest_asyncio.fixture
async def app(app_settings: AppSettings):
    application = create_app(app_settings)
    async with LifespanManager(application):
        yield application


@pytest_asyncio.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http


@pytest.fixture
def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture
def with_api_key(monkeypatch) -> str:
    key = "sk-teste-123"
    monkeypatch.setenv("OPENAI_API_KEY", key)
    return key


@pytest.fixture
def container(app):
    return app.state.container


@pytest.fixture
def make_wav():
    def _make(seconds: float = 1.0, rate: int = 16000) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(b"\x00\x00" * int(rate * seconds))
        return buffer.getvalue()

    return _make


@pytest.fixture
def wait_for_job():
    async def _wait(http, job_id: str, auth: dict, statuses: set[str], timeout: float = 5.0):
        deadline = time.monotonic() + timeout
        last: dict | None = None
        while time.monotonic() < deadline:
            response = await http.get(f"/api/v1/transcription-jobs/{job_id}", headers=auth)
            last = response.json()
            if last.get("status") in statuses:
                return last
            await asyncio.sleep(0.02)
        raise AssertionError(f"job não alcançou {statuses} (último: {last})")

    return _wait
