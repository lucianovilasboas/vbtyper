"""Engine e fábrica de sessões SQLAlchemy."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def database_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{Path(path)}"


def make_engine(path: Path) -> Engine:
    return create_engine(
        database_url(path),
        connect_args={"check_same_thread": False},
        future=True,
    )


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)
