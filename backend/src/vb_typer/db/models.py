"""Modelos persistidos no SQLite."""

from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from vb_typer.db.base import Base


class Transcription(Base):
    __tablename__ = "transcriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[str] = mapped_column(String(19), nullable=False, index=True)
    audio_path: Mapped[str | None] = mapped_column(Text)
    audio_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_s: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    words: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    transcribe_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    insert_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Como o texto foi entregue ("literal" ou "smart") e o que a transcrição
    # devolveu antes do ajuste, para auditar e poder voltar atrás.
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="literal")
    raw_text: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)

    # Rastreabilidade da importação do app 1.x (idempotência).
    legacy_source: Mapped[str | None] = mapped_column(String(255))
    legacy_id: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        UniqueConstraint("legacy_source", "legacy_id", name="uq_transcriptions_legacy"),
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    created_at: Mapped[str] = mapped_column(String(19), nullable=False, index=True)
    updated_at: Mapped[str] = mapped_column(String(19), nullable=False)
    started_at: Mapped[str | None] = mapped_column(String(19))
    finished_at: Mapped[str | None] = mapped_column(String(19))

    model: Mapped[str] = mapped_column(String(64), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="literal")
    filename: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    content_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_s: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    audio_path: Mapped[str | None] = mapped_column(Text)
    transcription_id: Mapped[int | None] = mapped_column(
        ForeignKey("transcriptions.id", ondelete="SET NULL")
    )
    error: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AppSetting(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="literal")
    week_start: Mapped[str] = mapped_column(String(16), nullable=False, default="monday")
    updated_at: Mapped[str] = mapped_column(String(19), nullable=False)
