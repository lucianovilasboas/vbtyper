"""Perfis de texto: padrões semeados no banco e perfis personalizados."""

from __future__ import annotations

ENDPOINT = "/api/v1/profiles"
BUILTIN_SLUGS = {
    "literal",
    "revisado",
    "email",
    "whatsapp",
    "programacao",
    "prompt",
    "academico",
    "curriculo",
    "carta",
    "ata",
}


async def test_builtin_profiles_are_listed(client, auth):
    response = await client.get(ENDPOINT, headers=auth)
    assert response.status_code == 200
    profiles = response.json()

    builtin = [item for item in profiles if item["builtin"]]
    assert len(builtin) == 10
    slugs = {item["slug"] for item in profiles}
    assert BUILTIN_SLUGS.issubset(slugs)
    assert all(item["instructions"] or item["slug"] == "literal" for item in builtin)
    # A ordem curada dos padrões é preservada.
    assert [item["slug"] for item in builtin][:3] == ["literal", "revisado", "email"]


async def test_create_custom_profile(client, auth):
    response = await client.post(
        ENDPOINT,
        headers=auth,
        json={
            "name": "Minha ata",
            "instructions": "Registre em tópicos, sem inventar decisões.",
            "options": {"tom": "formal", "concisao": "curto"},
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["slug"] == "minha-ata"
    assert body["builtin"] is False
    assert body["options"] == {"tom": "formal", "concisao": "curto"}

    listing = await client.get(ENDPOINT, headers=auth)
    assert "minha-ata" in [item["slug"] for item in listing.json()]


async def test_unknown_option_is_ignored(client, auth):
    response = await client.post(
        ENDPOINT,
        headers=auth,
        json={
            "name": "Sem opções válidas",
            "instructions": "Instruções suficientemente longas.",
            "options": {"tom": "cantado", "inventado": True},
        },
    )
    assert response.status_code == 201
    assert response.json()["options"] == {}


async def test_seeded_profile_can_be_edited_and_deleted(client, auth):
    patched = await client.patch(
        f"{ENDPOINT}/email", headers=auth, json={"name": "E-mail do trabalho"}
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "E-mail do trabalho"
    assert patched.json()["builtin"] is True

    deleted = await client.delete(f"{ENDPOINT}/ata", headers=auth)
    assert deleted.status_code == 204
    listing = await client.get(ENDPOINT, headers=auth)
    assert "ata" not in [item["slug"] for item in listing.json()]


async def test_literal_can_be_renamed_but_not_deleted(client, auth):
    renamed = await client.patch(f"{ENDPOINT}/literal", headers=auth, json={"name": "Texto cru"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Texto cru"
    assert renamed.json()["instructions"] == ""

    deleted = await client.delete(f"{ENDPOINT}/literal", headers=auth)
    assert deleted.status_code == 409
    assert deleted.json()["error"]["code"] == "conflict"


async def test_deleting_the_default_profile_falls_back_to_literal(client, auth):
    changed = await client.patch(
        "/api/v1/settings", headers=auth, json={"default_profile": "email"}
    )
    assert changed.status_code == 200
    assert changed.json()["default_profile"] == "email"

    assert (await client.delete(f"{ENDPOINT}/email", headers=auth)).status_code == 204

    settings = (await client.get("/api/v1/settings", headers=auth)).json()
    assert settings["default_profile"] == "literal"
    assert settings["mode"] == "literal"


async def test_seed_does_not_resurrect_a_deleted_profile(app, client, auth):
    assert (await client.delete(f"{ENDPOINT}/ata", headers=auth)).status_code == 204

    app.state.container.profiles.seed_defaults()

    listing = await client.get(ENDPOINT, headers=auth)
    assert "ata" not in [item["slug"] for item in listing.json()]


async def test_custom_can_be_updated_and_deleted(client, auth):
    created = (
        await client.post(
            ENDPOINT,
            headers=auth,
            json={"name": "Meu perfil", "instructions": "Instruções iniciais do perfil."},
        )
    ).json()
    slug = created["slug"]

    patched = await client.patch(
        f"{ENDPOINT}/{slug}",
        headers=auth,
        json={"name": "Meu perfil 2", "options": {"concisao": "curto"}},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Meu perfil 2"
    assert patched.json()["options"] == {"concisao": "curto"}

    deleted = await client.delete(f"{ENDPOINT}/{slug}", headers=auth)
    assert deleted.status_code == 204
    gone = await client.patch(f"{ENDPOINT}/{slug}", headers=auth, json={"name": "Zz"})
    assert gone.status_code == 404


async def test_duplicate_name_gets_unique_slug(client, auth):
    for _ in range(2):
        response = await client.post(
            ENDPOINT,
            headers=auth,
            json={"name": "Cópia", "instructions": "Instruções suficientes para o perfil."},
        )
        assert response.status_code == 201

    slugs = [item["slug"] for item in (await client.get(ENDPOINT, headers=auth)).json()]
    assert "copia" in slugs
    assert "copia-2" in slugs


async def test_short_instructions_are_rejected(client, auth):
    response = await client.post(
        ENDPOINT, headers=auth, json={"name": "Curto", "instructions": "curto"}
    )
    assert response.status_code == 422


async def test_continuous_flag_survives_the_round_trip(client, auth):
    created = await client.post(
        ENDPOINT,
        headers=auth,
        json={
            "name": "Fluxo",
            "instructions": "Una a fala em um parágrafo, mantendo o fio do raciocínio.",
            "options": {"continuo": True},
        },
    )
    assert created.status_code in (200, 201)
    slug = created.json()["slug"]
    assert created.json()["options"]["continuo"] is True

    listed = {item["slug"]: item for item in (await client.get(ENDPOINT, headers=auth)).json()}
    assert listed[slug]["options"]["continuo"] is True

    # Desligar a flag remove a chave (não grava "continuo": false).
    updated = await client.patch(f"{ENDPOINT}/{slug}", headers=auth, json={"options": {}})
    assert updated.status_code == 200
    assert "continuo" not in updated.json()["options"]


async def test_invalid_delivery_is_rejected(client, auth):
    response = await client.post(
        ENDPOINT,
        headers=auth,
        json={
            "name": "Destino inválido",
            "instructions": "Instruções suficientemente longas.",
            "options": {"delivery": "telepatia"},
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_delivery"


async def test_invalid_tool_is_rejected(client, auth):
    response = await client.post(
        ENDPOINT,
        headers=auth,
        json={
            "name": "Ferramenta inválida",
            "instructions": "Instruções suficientemente longas.",
            "options": {"tools": ["nao-existe"]},
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_tool"


async def test_literal_accepts_delivery_options(client, auth):
    response = await client.patch(
        f"{ENDPOINT}/literal",
        headers=auth,
        json={
            "name": "Transcrição fiel",
            "options": {"delivery": "tui", "tools": ["strip_markdown"]},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["options"]["delivery"] == "tui"
    assert body["options"]["tools"] == ["strip_markdown"]
