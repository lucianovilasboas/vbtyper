"""Perfis de texto: embutidos (somente leitura) e personalizados."""

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


async def test_builtin_cannot_be_edited_or_deleted(client, auth):
    patched = await client.patch(f"{ENDPOINT}/email", headers=auth, json={"name": "Outro"})
    assert patched.status_code == 409
    assert patched.json()["error"]["code"] == "conflict"

    deleted = await client.delete(f"{ENDPOINT}/email", headers=auth)
    assert deleted.status_code == 409


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
