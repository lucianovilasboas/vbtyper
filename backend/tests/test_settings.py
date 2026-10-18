"""Configurações editáveis e teste de conexão."""

from __future__ import annotations

import httpx


async def test_defaults_come_from_config(client, auth):
    response = await client.get("/api/v1/settings", headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "gpt-4o-mini-transcribe"
    assert body["language"] == "pt"
    assert body["week_start"] == "monday"
    assert body["api_key_configured"] is False
    assert set(body["allowed_models"]) == {"gpt-4o-mini-transcribe", "gpt-transcribe"}


async def test_patch_updates_model_and_language(client, auth):
    response = await client.patch(
        "/api/v1/settings",
        headers=auth,
        json={"model": "gpt-transcribe", "language": "en", "week_start": "sunday"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "gpt-transcribe"
    assert body["language"] == "en"
    assert body["week_start"] == "sunday"

    again = await client.get("/api/v1/settings", headers=auth)
    assert again.json()["model"] == "gpt-transcribe"


async def test_patch_rejects_unknown_model(client, auth):
    response = await client.patch(
        "/api/v1/settings", headers=auth, json={"model": "modelo-inexistente"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_model"


async def test_patch_rejects_bad_week_start(client, auth):
    response = await client.patch("/api/v1/settings", headers=auth, json={"week_start": "quarta"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_week_start"


async def test_connection_test_is_read_only(client, auth, with_api_key, respx_mock):
    route = respx_mock.get("https://api.openai.com/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "a"}, {"id": "b"}]})
    )
    response = await client.post("/api/v1/settings/test", headers=auth)
    assert response.status_code == 200
    assert route.called
    assert response.json() == {
        "ok": True,
        "models_available": 2,
        "message": "Conexão com a OpenAI verificada.",
    }
