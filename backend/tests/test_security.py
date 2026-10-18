"""Token, Host, Origin e formato de erro."""

from __future__ import annotations

from tests.conftest import TEST_TOKEN


async def test_missing_token_is_rejected(client):
    response = await client.get("/api/v1/settings")
    assert response.status_code == 401
    body = response.json()["error"]
    assert body["code"] == "unauthorized"
    assert body["request_id"]


async def test_wrong_token_is_rejected(client):
    response = await client.get("/api/v1/settings", headers={"Authorization": "Bearer errado"})
    assert response.status_code == 401


async def test_valid_token_grants_access(client, auth):
    response = await client.get("/api/v1/settings", headers=auth)
    assert response.status_code == 200


async def test_foreign_origin_is_forbidden(client, auth):
    response = await client.get(
        "/api/v1/settings", headers={**auth, "Origin": "http://atacante.example"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "invalid_origin"


async def test_local_origin_is_accepted(client, auth):
    response = await client.get(
        "/api/v1/settings", headers={**auth, "Origin": "http://127.0.0.1:8765"}
    )
    assert response.status_code == 200


async def test_foreign_host_is_rejected(client, auth):
    response = await client.get("/api/v1/settings", headers={**auth, "Host": "atacante.example"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_host"


async def test_health_works_without_token(client):
    assert (await client.get("/api/v1/health")).status_code == 200


async def test_request_id_header_present(client, auth):
    response = await client.get("/api/v1/settings", headers=auth)
    assert response.headers.get("X-Request-ID")


async def test_authorization_scheme_must_be_bearer(client):
    response = await client.get(
        "/api/v1/settings", headers={"Authorization": f"Token {TEST_TOKEN}"}
    )
    assert response.status_code == 401


async def test_database_is_private(client, app):
    database = app.state.container.paths.database
    assert (database.stat().st_mode & 0o777) == 0o600


def test_token_file_is_created_private(tmp_path):
    from vb_typer.core.paths import AppPaths
    from vb_typer.core.security import load_or_create_token

    paths = AppPaths(
        config_dir=tmp_path,
        data_dir=tmp_path,
        database=tmp_path / "db.sqlite",
        audio_dir=tmp_path / "audio",
        token_file=tmp_path / "api-token",
    )
    token = load_or_create_token(paths)
    assert len(token) >= 32
    assert (paths.token_file.stat().st_mode & 0o777) == 0o600
    assert load_or_create_token(paths) == token
