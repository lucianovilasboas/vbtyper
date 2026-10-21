"""Versões do ditado: aplicar outro perfil sem re-transcrever o áudio."""

from __future__ import annotations

import json

import httpx

CHAT = "https://api.openai.com/v1/chat/completions"
ENDPOINT = "/api/v1/transcriptions"


def _row(container, *, text="texto original", raw_text="texto original"):
    return container.history.record(
        text=text,
        raw_text=raw_text,
        duration_s=10,
        model="gpt-4o-mini-transcribe",
        language="pt",
        mode="literal",
        profile="literal",
    )


def _chat(text: str, prompt_tokens: int = 120, completion_tokens: int = 80):
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": text}}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
        },
    )


async def test_render_creates_a_version_and_updates_the_text(
    client, auth, container, with_api_key, respx_mock
):
    row = _row(container)
    respx_mock.post(CHAT).mock(return_value=_chat("Assunto: erro\n\nOi Rafael, verifique."))

    response = await client.post(
        f"{ENDPOINT}/{row.id}/render", headers=auth, json={"profile": "email"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["profile"] == "email"
    assert body["mode"] == "smart"
    assert body["text"].startswith("Assunto:")
    assert body["raw_text"] == "texto original"
    assert len(body["versions"]) == 1
    version = body["versions"][0]
    assert version["profile"] == "email"
    assert version["prompt_tokens"] == 120
    assert version["completion_tokens"] == 80
    assert version["cost_usd"] > 0


async def test_render_starts_from_the_raw_text(client, auth, container, with_api_key, respx_mock):
    row = _row(container, text="texto já editado", raw_text="texto original")
    route = respx_mock.post(CHAT).mock(return_value=_chat("novo texto"))

    await client.post(f"{ENDPOINT}/{row.id}/render", headers=auth, json={"profile": "ata"})

    sent = json.loads(route.calls.last.request.content)
    assert sent["messages"][1]["content"] == "texto original"
    system = sent["messages"][0]["content"].lower()
    assert "ata" in system or "reunião" in system


async def test_render_literal_is_rejected(client, auth, container):
    row = _row(container)

    response = await client.post(
        f"{ENDPOINT}/{row.id}/render", headers=auth, json={"profile": "literal"}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_profile"


async def test_render_failure_keeps_the_current_text(
    client, auth, container, with_api_key, respx_mock
):
    row = _row(container)
    respx_mock.post(CHAT).mock(
        return_value=httpx.Response(500, json={"error": {"message": "boom"}})
    )

    response = await client.post(
        f"{ENDPOINT}/{row.id}/render", headers=auth, json={"profile": "email"}
    )

    assert response.status_code == 502
    fresh = await client.get(f"{ENDPOINT}/{row.id}", headers=auth)
    assert fresh.json()["text"] == "texto original"
    assert fresh.json()["versions"] == []


async def test_render_without_api_key_is_unavailable(client, auth, container):
    row = _row(container)

    response = await client.post(
        f"{ENDPOINT}/{row.id}/render", headers=auth, json={"profile": "email"}
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "api_key_missing"


async def test_render_unknown_profile_is_not_found(client, auth, container):
    row = _row(container)

    response = await client.post(
        f"{ENDPOINT}/{row.id}/render", headers=auth, json={"profile": "nao-existe"}
    )

    assert response.status_code == 404
