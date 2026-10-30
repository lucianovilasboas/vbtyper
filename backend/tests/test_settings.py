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


async def test_default_profile_can_be_changed(client, auth):
    response = await client.patch(
        "/api/v1/settings", headers=auth, json={"default_profile": "email"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["default_profile"] == "email"
    # O modo acompanha: qualquer coisa diferente de literal é "smart".
    assert body["mode"] == "smart"


async def test_unknown_default_profile_is_rejected(client, auth):
    response = await client.patch(
        "/api/v1/settings", headers=auth, json={"default_profile": "nao-existe"}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_profile"


async def test_mode_keeps_the_default_profile_in_sync(client, auth):
    await client.patch("/api/v1/settings", headers=auth, json={"mode": "smart"})

    body = (await client.get("/api/v1/settings", headers=auth)).json()
    assert body["default_profile"] == "revisado"


async def test_smart_model_can_be_changed(client, auth):
    response = await client.patch("/api/v1/settings", headers=auth, json={"smart_model": "gpt-4o"})

    assert response.status_code == 200
    body = response.json()
    assert body["smart_model"] == "gpt-4o"
    assert "gpt-4o" in body["allowed_smart_models"]
    # O preço vem da tabela do domínio (entrada, saída por 1M).
    assert body["text_prices"]["gpt-4o"] == [2.5, 10.0]


async def test_invalid_smart_model_is_rejected(client, auth):
    response = await client.patch(
        "/api/v1/settings", headers=auth, json={"smart_model": "nao-existe"}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_smart_model"


async def test_hotkeys_come_with_the_defaults(client, auth):
    """A aba Configurações mostra as combinações e o padrão para restaurar."""
    body = (await client.get("/api/v1/settings", headers=auth)).json()

    assert body["hotkeys"] == {
        "profile_next": "ctrl+alt+Tab",
        "profile_previous": "ctrl+alt+shift+Tab",
        "profile_default": "ctrl+alt+0",
    }
    assert body["default_hotkeys"] == body["hotkeys"]


async def test_patch_updates_hotkeys_and_normalizes(client, auth):
    response = await client.patch(
        "/api/v1/settings",
        headers=auth,
        json={"hotkeys": {"profile_next": "ALT+CTRL+F9", "profile_previous": "ctrl+alt+F10"}},
    )

    assert response.status_code == 200
    hotkeys = response.json()["hotkeys"]
    # Modificadores em ordem canônica; a ação não enviada continua no padrão.
    assert hotkeys["profile_next"] == "ctrl+alt+F9"
    assert hotkeys["profile_previous"] == "ctrl+alt+F10"
    assert hotkeys["profile_default"] == "ctrl+alt+0"


async def test_patch_rejects_hotkey_without_modifier(client, auth):
    response = await client.patch(
        "/api/v1/settings", headers=auth, json={"hotkeys": {"profile_next": "Tab"}}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_hotkey"


async def test_patch_rejects_ctrl_super_combo(client, auth):
    """Ctrl+Super é o atalho de gravar: um perfil ali começaria um ditado."""
    response = await client.patch(
        "/api/v1/settings", headers=auth, json={"hotkeys": {"profile_next": "ctrl+super+Tab"}}
    )

    assert response.status_code == 400
    assert "gravar" in response.json()["error"]["message"]


async def test_patch_rejects_repeated_combo(client, auth):
    response = await client.patch(
        "/api/v1/settings",
        headers=auth,
        json={"hotkeys": {"profile_next": "ctrl+alt+Tab", "profile_previous": "alt+ctrl+Tab"}},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_hotkey"


async def test_patch_rejects_unknown_key(client, auth):
    response = await client.patch(
        "/api/v1/settings", headers=auth, json={"hotkeys": {"profile_next": "ctrl+alt+Tecla"}}
    )

    assert response.status_code == 400
    assert "Tecla desconhecida" in response.json()["error"]["message"]


async def test_version_changes_only_when_something_changes(client, auth):
    first = (await client.get("/api/v1/settings", headers=auth)).json()["version"]
    assert first and len(first) == 12

    # Ler de novo não muda a versão (é o que os clientes comparam a cada 2 s).
    again = (await client.get("/api/v1/settings", headers=auth)).json()["version"]
    assert again == first

    # Um PATCH que não altera nada também não pode parecer mudança.
    await client.patch("/api/v1/settings", headers=auth, json={"language": "pt"})
    assert (await client.get("/api/v1/settings", headers=auth)).json()["version"] == first

    await client.patch("/api/v1/settings", headers=auth, json={"language": "en"})
    changed = (await client.get("/api/v1/settings", headers=auth)).json()["version"]
    assert changed != first


async def test_version_changes_for_each_editable_choice(client, auth):
    """Todo campo que o cliente aplica precisa entrar na impressão digital."""
    seen = {(await client.get("/api/v1/settings", headers=auth)).json()["version"]}
    for body in (
        {"model": "gpt-transcribe"},
        {"smart_model": "gpt-4.1-mini"},
        {"default_profile": "revisado"},
        {"week_start": "sunday"},
        {"hotkeys": {"profile_next": "ctrl+alt+F7"}},
    ):
        response = await client.patch("/api/v1/settings", headers=auth, json=body)
        assert response.status_code == 200, body
        assert response.json()["version"]
        seen.add(response.json()["version"])

    assert len(seen) == 6  # o inicial + os cinco, todos distintos


async def test_version_follows_the_profile_list(client, auth):
    """Renomear ou criar perfil precisa chegar ao cliente pela versão."""
    base = (await client.get("/api/v1/settings", headers=auth)).json()["version"]

    created = await client.post(
        "/api/v1/profiles",
        headers=auth,
        json={"name": "Perfil novo", "instructions": "Deixe o texto direto e curto."},
    )
    assert created.status_code == 201
    after_create = (await client.get("/api/v1/settings", headers=auth)).json()["version"]
    assert after_create != base

    slug = created.json()["slug"]
    renamed = await client.patch(
        f"/api/v1/profiles/{slug}", headers=auth, json={"name": "Perfil renomeado"}
    )
    assert renamed.status_code == 200
    after_rename = (await client.get("/api/v1/settings", headers=auth)).json()["version"]
    assert after_rename != after_create
