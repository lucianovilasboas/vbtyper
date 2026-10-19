"""Esquemas de estatísticas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from vb_typer.domain.enums import Granularity


class StatsPoint(BaseModel):
    bucket: str
    label: str
    count: int
    seconds: float
    words: int


class StatsSummary(BaseModel):
    total: int
    seconds: float
    bytes: int
    chars: int
    words: int
    failures: int
    not_inserted: int
    avg_ms: float
    first_at: str | None = None
    last_at: str | None = None
    no_duration: int
    cost_usd: float


class StatsLongest(BaseModel):
    text: str
    duration_s: float
    words: int


class StatsInsights(BaseModel):
    words_per_minute: float
    dictations_per_active_day: float
    average_duration: float
    peak_hour: str
    peak_hour_count: int
    api_average_ms: float
    api_p95_ms: int
    longest: StatsLongest | None = None
    failure_rate: float


class StatsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    date_from: str = Field(alias="from")
    date_to: str = Field(alias="to")
    granularity: Granularity
    summary: StatsSummary
    series: list[StatsPoint]
    insights: StatsInsights
