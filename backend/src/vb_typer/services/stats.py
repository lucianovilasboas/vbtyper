"""Estatísticas agregadas sobre o histórico."""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, sessionmaker

from vb_typer.core.config import AppSettings
from vb_typer.core.timeutil import local_stamp, normalize_bound, parse_local_stamp
from vb_typer.db.models import Transcription
from vb_typer.domain.enums import Granularity
from vb_typer.services.common import cost_usd

MAX_BUCKETS = 5000


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def _week_start_index(week_start: str) -> int:
    return 0 if week_start == "monday" else 6


def _floor(moment: datetime, granularity: Granularity, week_start: str) -> datetime:
    base = moment.replace(minute=0, second=0, microsecond=0)
    if granularity is Granularity.HOUR:
        return base
    base = base.replace(hour=0)
    if granularity is Granularity.DAY:
        return base
    if granularity is Granularity.WEEK:
        delta = (base.weekday() - _week_start_index(week_start)) % 7
        return base - timedelta(days=delta)
    return base.replace(day=1)


def _advance(moment: datetime, granularity: Granularity) -> datetime:
    if granularity is Granularity.HOUR:
        return moment + timedelta(hours=1)
    if granularity is Granularity.DAY:
        return moment + timedelta(days=1)
    if granularity is Granularity.WEEK:
        return moment + timedelta(days=7)
    if moment.month == 12:
        return moment.replace(year=moment.year + 1, month=1)
    return moment.replace(month=moment.month + 1)


def _key(moment: datetime, granularity: Granularity) -> str:
    if granularity is Granularity.HOUR:
        return moment.strftime("%Y-%m-%d %H")
    if granularity is Granularity.MONTH:
        return moment.strftime("%Y-%m")
    return moment.strftime("%Y-%m-%d")


def _label(moment: datetime, granularity: Granularity) -> str:
    if granularity is Granularity.HOUR:
        return moment.strftime("%H:00")
    if granularity is Granularity.MONTH:
        return moment.strftime("%m/%Y")
    return moment.strftime("%d/%m")


class StatsService:
    def __init__(self, session_factory: sessionmaker[Session], settings: AppSettings) -> None:
        self.session_factory = session_factory
        self.settings = settings

    def bounds(
        self, date_from: str | None, date_to: str | None, default_days: int = 30
    ) -> tuple[str, str]:
        end = normalize_bound(date_to, upper=True) or local_stamp()
        start = normalize_bound(date_from)
        if start is None:
            start_dt = parse_local_stamp(end) - timedelta(days=default_days - 1)
            start_dt = start_dt.replace(hour=0, minute=0, second=0)
            start = _stamp(start_dt)
        return start, end

    def summary(self, date_from: str, date_to: str) -> dict:
        window = (
            Transcription.created_at >= date_from,
            Transcription.created_at <= date_to,
        )
        with self.session_factory() as session:
            row = session.execute(
                select(
                    func.count(Transcription.id),
                    func.coalesce(func.sum(Transcription.duration_s), 0.0),
                    func.coalesce(func.sum(Transcription.audio_bytes), 0),
                    func.coalesce(func.sum(func.length(Transcription.text)), 0),
                    func.coalesce(func.sum(Transcription.words), 0),
                    func.coalesce(func.sum(case((Transcription.error.isnot(None), 1), else_=0)), 0),
                    func.coalesce(
                        func.sum(case((Transcription.inserted.is_(False), 1), else_=0)), 0
                    ),
                    func.coalesce(func.avg(func.nullif(Transcription.transcribe_ms, 0)), 0.0),
                    func.min(Transcription.created_at),
                    func.max(Transcription.created_at),
                ).where(*window)
            ).one()
            priced = session.execute(
                select(
                    Transcription.model,
                    func.coalesce(func.sum(Transcription.duration_s), 0.0),
                )
                .where(*window)
                .group_by(Transcription.model)
            ).all()

        total = int(row[0])
        return {
            "total": total,
            "seconds": float(row[1]),
            "bytes": int(row[2]),
            "chars": int(row[3]),
            "words": int(row[4]),
            "failures": int(row[5]),
            "not_inserted": int(row[6]),
            "avg_ms": float(row[7]),
            "first_at": row[8],
            "last_at": row[9],
            "cost_usd": sum(cost_usd(model, seconds) for model, seconds in priced),
        }

    def series(self, date_from: str, date_to: str, granularity: Granularity) -> list[dict]:
        week_start = self.settings.week_start
        start = _floor(parse_local_stamp(date_from), granularity, week_start)
        end = _floor(parse_local_stamp(date_to), granularity, week_start)
        buckets: dict[str, dict] = {}
        cursor = start
        while cursor <= end:
            buckets[_key(cursor, granularity)] = {
                "bucket": _key(cursor, granularity),
                "label": _label(cursor, granularity),
                "count": 0,
                "seconds": 0.0,
                "words": 0,
            }
            if len(buckets) > MAX_BUCKETS:
                raise ValueError("Intervalo grande demais para essa granularidade.")
            cursor = _advance(cursor, granularity)

        with self.session_factory() as session:
            rows = session.execute(
                select(
                    Transcription.created_at,
                    Transcription.duration_s,
                    Transcription.words,
                ).where(
                    Transcription.created_at >= date_from,
                    Transcription.created_at <= date_to,
                )
            ).all()

        for created_at, duration_s, words in rows:
            key = _key(_floor(parse_local_stamp(created_at), granularity, week_start), granularity)
            bucket = buckets.get(key)
            if bucket is None:
                continue
            bucket["count"] += 1
            bucket["seconds"] += float(duration_s or 0.0)
            bucket["words"] += int(words or 0)
        return list(buckets.values())

    def insights(self, date_from: str, date_to: str) -> dict:
        summary = self.summary(date_from, date_to)
        hours = self.series(date_from, date_to, Granularity.HOUR)
        days = self.series(date_from, date_to, Granularity.DAY)
        with self.session_factory() as session:
            longest = session.execute(
                select(Transcription.text, Transcription.duration_s, Transcription.words)
                .where(
                    Transcription.created_at >= date_from,
                    Transcription.created_at <= date_to,
                )
                .order_by(Transcription.duration_s.desc())
                .limit(1)
            ).first()
            latencies = [
                row[0]
                for row in session.execute(
                    select(Transcription.transcribe_ms)
                    .where(
                        Transcription.transcribe_ms > 0,
                        Transcription.created_at >= date_from,
                        Transcription.created_at <= date_to,
                    )
                    .order_by(Transcription.transcribe_ms)
                ).all()
            ]

        minutes = summary["seconds"] / 60
        active_days = max(1, sum(1 for day in days if day["count"]))
        peak = max(hours, key=lambda item: item["count"], default={"label": "—", "count": 0})
        p95 = latencies[max(0, math.ceil(0.95 * len(latencies)) - 1)] if latencies else 0
        total = summary["total"]
        return {
            "words_per_minute": (summary["words"] / minutes) if minutes else 0.0,
            "dictations_per_active_day": (total / active_days) if active_days else 0.0,
            "average_duration": (summary["seconds"] / total) if total else 0.0,
            "peak_hour": peak["label"],
            "peak_hour_count": peak["count"],
            "api_average_ms": summary["avg_ms"],
            "api_p95_ms": p95,
            "longest": (
                {"text": longest[0], "duration_s": float(longest[1]), "words": int(longest[2])}
                if longest
                else None
            ),
            "failure_rate": (summary["failures"] / total) if total else 0.0,
        }
