"""Estatísticas: resumo, séries e indicadores."""

from __future__ import annotations

from datetime import datetime, timedelta


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def _record(container, *, text, when, duration, model="gpt-4o-mini-transcribe"):
    return container.history.record(
        text=text,
        duration_s=duration,
        model=model,
        language="pt",
        transcribe_ms=1000,
        inserted=True,
        created_at=_stamp(when),
    )


async def test_summary_over_default_window(client, auth, container):
    now = datetime.now()
    _record(container, text="a b c", when=now, duration=60)
    _record(container, text="d e", when=now - timedelta(days=1), duration=30)
    _record(container, text="antigo demais", when=now - timedelta(days=45), duration=120)

    response = await client.get("/api/v1/stats", headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert body["from"].startswith((now - timedelta(days=29)).strftime("%Y-%m-%d"))
    assert body["summary"]["total"] == 2
    assert body["summary"]["seconds"] == 90.0
    assert body["summary"]["words"] == 5
    assert round(body["summary"]["cost_usd"], 6) == round(90 / 60 * 0.003, 6)
    assert len(body["series"]) == 30


async def test_day_series_buckets_include_empty_days(client, auth, container):
    now = datetime.now()
    _record(container, text="hoje", when=now, duration=10)
    start = (now - timedelta(days=2)).strftime("%Y-%m-%d")
    end = now.strftime("%Y-%m-%d")
    response = await client.get(
        "/api/v1/stats",
        headers=auth,
        params={"from": start, "to": end, "granularity": "day"},
    )
    series = response.json()["series"]
    assert len(series) == 3
    assert series[-1]["count"] == 1
    assert series[0]["count"] == 0
    assert series[-1]["words"] == 1


async def test_month_granularity(client, auth, container):
    now = datetime.now()
    _record(container, text="mes atual", when=now, duration=30)
    start = (now - timedelta(days=70)).strftime("%Y-%m-%d")
    end = now.strftime("%Y-%m-%d")
    response = await client.get(
        "/api/v1/stats",
        headers=auth,
        params={"from": start, "to": end, "granularity": "month"},
    )
    series = response.json()["series"]
    assert 3 <= len(series) <= 4
    assert sum(point["count"] for point in series) == 1


async def test_week_granularity_uses_monday_start(client, auth, container):
    now = datetime.now()
    monday = (now - timedelta(days=now.weekday())).replace(hour=10, minute=0, second=0)
    _record(container, text="segunda", when=monday, duration=20)
    start = monday.strftime("%Y-%m-%d")
    end = (monday + timedelta(days=6)).strftime("%Y-%m-%d")
    response = await client.get(
        "/api/v1/stats",
        headers=auth,
        params={"from": start, "to": end, "granularity": "week"},
    )
    series = response.json()["series"]
    assert len(series) == 1
    assert series[0]["count"] == 1


async def test_hour_granularity_covers_a_full_day(client, auth, container):
    now = datetime.now()
    _record(container, text="hora", when=now.replace(hour=9, minute=30), duration=5)
    day = now.strftime("%Y-%m-%d")
    response = await client.get(
        "/api/v1/stats",
        headers=auth,
        params={"from": day, "to": day, "granularity": "hour"},
    )
    series = response.json()["series"]
    assert len(series) == 24
    assert series[9]["count"] == 1


async def test_insights_expose_derived_metrics(client, auth, container):
    now = datetime.now()
    _record(container, text="uma duas tres", when=now, duration=60)
    response = await client.get("/api/v1/stats", headers=auth)
    insights = response.json()["insights"]
    assert insights["words_per_minute"] == 3.0
    assert insights["api_p95_ms"] == 1000
    assert insights["longest"]["text"] == "uma duas tres"
    assert insights["peak_hour"].endswith(":00")


async def test_invalid_range_is_rejected(client, auth):
    response = await client.get(
        "/api/v1/stats", headers=auth, params={"from": "2026-05-10", "to": "2026-05-01"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_range"


async def test_invalid_granularity_is_rejected(client, auth):
    response = await client.get("/api/v1/stats", headers=auth, params={"granularity": "semana"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_average_duration_ignores_unknown_durations(client, auth, container):
    """Ditados sem duração (WebM antigo) não podem puxar a média para baixo."""
    now = datetime.now()
    _record(container, text="vinte", when=now, duration=20)
    _record(container, text="quarenta", when=now, duration=40)
    _record(container, text="sem duração", when=now, duration=0)

    response = await client.get("/api/v1/stats", headers=auth)
    body = response.json()

    assert body["summary"]["total"] == 3
    assert body["summary"]["no_duration"] == 1
    assert body["summary"]["seconds"] == 60.0
    assert body["insights"]["average_duration"] == 30.0
