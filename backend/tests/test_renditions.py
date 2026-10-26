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


async def test_render_uses_the_configured_text_model(
    client, auth, container, with_api_key, respx_mock
):
    """O modelo vem das configurações (banco), não do ambiente."""
    await client.patch("/api/v1/settings", headers=auth, json={"smart_model": "gpt-4.1-mini"})
    row = _row(container)
    route = respx_mock.post(CHAT).mock(return_value=_chat("novo"))

    response = await client.post(
        f"{ENDPOINT}/{row.id}/render", headers=auth, json={"profile": "email"}
    )

    assert response.status_code == 200
    sent = json.loads(route.calls.last.request.content)
    assert sent["model"] == "gpt-4.1-mini"
    assert response.json()["versions"][0]["model"] == "gpt-4.1-mini"


async def test_profile_model_overrides_the_global(
    client, auth, container, with_api_key, respx_mock
):
    await client.patch("/api/v1/settings", headers=auth, json={"smart_model": "gpt-4o-mini"})
    profile = (
        await client.post(
            "/api/v1/profiles",
            headers=auth,
            json={
                "name": "Caro",
                "instructions": "Organize em tópicos, sem inventar.",
                "options": {"modelo": "gpt-4o"},
            },
        )
    ).json()
    row = _row(container)
    route = respx_mock.post(CHAT).mock(return_value=_chat("ok"))

    response = await client.post(
        f"{ENDPOINT}/{row.id}/render", headers=auth, json={"profile": profile["slug"]}
    )

    assert response.status_code == 200
    sent = json.loads(route.calls.last.request.content)
    assert sent["model"] == "gpt-4o"
    assert response.json()["versions"][0]["model"] == "gpt-4o"


async def test_items_are_composed_into_the_prompt(
    client, auth, container, with_api_key, respx_mock
):
    profile = (
        await client.post(
            "/api/v1/profiles",
            headers=auth,
            json={
                "name": "Com regras",
                "instructions": "Reescreva o texto para uma mensagem.",
                "options": {"items": ["não usar emojis", "máximo 5 linhas"]},
            },
        )
    ).json()
    row = _row(container)
    route = respx_mock.post(CHAT).mock(return_value=_chat("ok"))

    await client.post(
        f"{ENDPOINT}/{row.id}/render", headers=auth, json={"profile": profile["slug"]}
    )

    system = json.loads(route.calls.last.request.content)["messages"][0]["content"]
    assert "não usar emojis" in system
    assert "máximo 5 linhas" in system


async def test_profile_with_invalid_model_is_rejected(client, auth):
    response = await client.post(
        "/api/v1/profiles",
        headers=auth,
        json={
            "name": "Modelo errado",
            "instructions": "Instruções suficientes para o perfil.",
            "options": {"modelo": "nao-existe"},
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_smart_model"


async def test_too_many_items_are_rejected(client, auth):
    response = await client.post(
        "/api/v1/profiles",
        headers=auth,
        json={
            "name": "Itens demais",
            "instructions": "Instruções suficientes para o perfil.",
            "options": {"items": [f"regra {index}" for index in range(13)]},
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "too_many_items"


async def test_render_never_uses_the_continuity_context(
    client, auth, container, with_api_key, respx_mock
):
    """Re-render é reprocessamento, não continuação: o contexto não entra."""
    created = await client.post(
        "/api/v1/profiles",
        headers=auth,
        json={
            "name": "Fluxo",
            "instructions": "Una a fala em um parágrafo, mantendo o fio do raciocínio.",
            "options": {"continuo": True},
        },
    )
    slug = created.json()["slug"]
    container.history.record(
        text="ditado anterior que não deve entrar",
        duration_s=5,
        model="gpt-4o-mini-transcribe",
        language="pt",
    )
    row = _row(container)
    respx_mock.post(CHAT).mock(return_value=_chat("texto ajustado"))

    response = await client.post(
        f"{ENDPOINT}/{row.id}/render", headers=auth, json={"profile": slug}
    )

    assert response.status_code == 200
    body = json.loads(respx_mock.calls[-1].request.content)
    assert "[DITADOS ANTERIORES" not in body["messages"][1]["content"]
    assert body["messages"][1]["content"] == "texto original"


async def test_render_applies_the_delivery_pipeline(
    client, auth, container, with_api_key, respx_mock
):
    profile = container.profiles.create(
        name="TUI render",
        instructions="Entregue um comando curto e objetivo, sem enfeites.",
        options={"delivery": "tui"},
    )
    row = _row(container)
    respx_mock.post(CHAT).mock(return_value=_chat("a\nb\t\x1b[31m"))

    response = await client.post(
        f"{ENDPOINT}/{row.id}/render", headers=auth, json={"profile": profile.slug}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "a b"
    assert body["raw_text"] == "texto original"
    assert body["delivery"] == "tui"
    assert "single_line" in body["tools"]
