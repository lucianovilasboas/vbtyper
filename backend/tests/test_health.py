"""Saúde, prontidão e índice."""

from __future__ import annotations


async def test_health_is_public(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert "api_key" not in body


async def test_ready_reports_database_and_key_state(client, with_api_key):
    response = await client.get("/api/v1/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["database"] is True
    assert body["api_key_configured"] is True
    assert "gpt-4o-mini-transcribe" in body["models"]


async def test_ready_without_key(client):
    response = await client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.json()["api_key_configured"] is False


async def test_index_points_to_docs(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json()["docs"] == "/docs"


async def test_openapi_is_available(client):
    response = await client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/transcription-jobs" in paths
    assert "/api/v1/stats" in paths
