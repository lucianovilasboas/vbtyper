"""Histórico: listagem, filtros, marcação de inserção, CSV e remoção."""

from __future__ import annotations

from datetime import datetime, timedelta

from vb_typer.core.timeutil import local_stamp


def _seed(container, count: int = 3):
    base = datetime.now() - timedelta(days=count)
    ids = []
    for index in range(count):
        moment = base + timedelta(days=index)
        row = container.history.record(
            text=f"ditado numero {index}",
            duration_s=10.0 + index,
            model="gpt-4o-mini-transcribe",
            language="pt",
            transcribe_ms=500 + index,
            inserted=index % 2 == 0,
            created_at=local_stamp(moment),
        )
        ids.append(row.id)
    return ids


async def test_list_is_paginated_newest_first(client, auth, container):
    ids = _seed(container, 3)
    response = await client.get("/api/v1/transcriptions", headers=auth, params={"limit": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["limit"] == 2
    assert [item["id"] for item in body["items"]] == [ids[2], ids[1]]


async def test_filters_by_inserted_and_search(client, auth, container):
    _seed(container, 3)
    response = await client.get("/api/v1/transcriptions", headers=auth, params={"inserted": False})
    assert response.json()["total"] == 1
    response = await client.get("/api/v1/transcriptions", headers=auth, params={"q": "numero 1"})
    assert response.json()["total"] == 1


async def test_patch_records_insertion(client, auth, container):
    ids = _seed(container, 1)
    response = await client.patch(
        f"/api/v1/transcriptions/{ids[0]}",
        headers=auth,
        json={"inserted": True, "insert_ms": 320},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["inserted"] is True
    assert body["insert_ms"] == 320
    assert body["created_at"].count("T") == 1  # formato ISO


async def test_detail_and_delete(client, auth, container):
    ids = _seed(container, 1)
    detail = await client.get(f"/api/v1/transcriptions/{ids[0]}", headers=auth)
    assert detail.status_code == 200
    assert detail.json()["text"] == "ditado numero 0"

    removed = await client.delete(f"/api/v1/transcriptions/{ids[0]}", headers=auth)
    assert removed.status_code == 204
    again = await client.get(f"/api/v1/transcriptions/{ids[0]}", headers=auth)
    assert again.status_code == 404


async def test_csv_export_uses_bom_and_semicolon(client, auth, container):
    _seed(container, 2)
    response = await client.get("/api/v1/transcriptions/export.csv", headers=auth)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    text = response.content.decode("utf-8-sig")
    lines = text.strip().splitlines()
    assert lines[0].startswith("id;created_at;text")
    assert len(lines) == 3
    assert "ditado numero 0" in text
