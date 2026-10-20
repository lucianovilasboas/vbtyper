"""Estatísticas agregadas do histórico."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from vb_typer.api.deps import ContainerDep
from vb_typer.domain.enums import Granularity
from vb_typer.domain.errors import DomainError
from vb_typer.schemas.stats import StatsResponse

router = APIRouter(prefix="/stats", tags=["estatísticas"])


@router.get("", response_model=StatsResponse)
def get_stats(
    container: ContainerDep,
    granularity: Granularity = Granularity.DAY,
    date_from: Annotated[str | None, Query(alias="from")] = None,
    date_to: Annotated[str | None, Query(alias="to")] = None,
) -> StatsResponse:
    start, end = container.stats.bounds(date_from, date_to)
    if start > end:
        raise DomainError("O início do intervalo é posterior ao fim.", code="invalid_range")
    summary = container.stats.summary(start, end)
    try:
        series = container.stats.series(start, end, granularity)
    except ValueError as exc:
        raise DomainError(str(exc), code="range_too_large") from exc
    insights = container.stats.insights(start, end)
    return StatsResponse.model_validate(
        {
            "from": start,
            "to": end,
            "granularity": granularity,
            "summary": summary,
            "series": series,
            "hours": container.stats.hours_of_day(start, end),
            "insights": insights,
        }
    )
