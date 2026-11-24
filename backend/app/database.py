"""Database engine and request-scoped session helpers."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""


settings = get_settings()
connect_args = (
    {"check_same_thread": False} if settings.database.url.startswith("sqlite") else {}
)
engine = create_engine(
    settings.database.url,
    pool_pre_ping=True,
    connect_args=connect_args,
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Provide one SQLAlchemy session for an API request.

    Yields:
        An open database session.
    """
    with SessionLocal() as session:
        yield session
