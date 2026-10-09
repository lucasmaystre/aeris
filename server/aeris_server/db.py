import os
from datetime import datetime
from functools import cache

from sqlalchemy import Boolean, DateTime, Engine, ForeignKey, Text, create_engine, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import NullPool

DATABASE_URL_VAR = "AERIS_DATABASE_URL"


def database_url() -> str:
    """Read the database URL from the environment, accepting Neon's `postgresql://` form."""
    url = os.environ.get(DATABASE_URL_VAR)
    if not url:
        raise RuntimeError(f"{DATABASE_URL_VAR} is not set.")
    return to_psycopg_url(url)


def to_psycopg_url(url: str) -> str:
    """Make SQLAlchemy use psycopg 3, whatever Postgres scheme the URL uses."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url.removeprefix(prefix)
    return url


@cache
def engine() -> Engine:
    # No client-side pool: on serverless, each instance is short-lived, and Neon's pooler pools.
    return create_engine(database_url(), poolclass=NullPool)


def session() -> Session:
    return Session(engine())


class Base(DeclarativeBase):
    pass


class Note(Base):
    __tablename__ = "note"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Set explicitly when content changes, so derived updates (e.g. tags) leave it alone.
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    content: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    deleted: Mapped[bool] = mapped_column(Boolean, server_default="false")


class NoteRevision(Base):
    __tablename__ = "note_revision"

    id: Mapped[int] = mapped_column(primary_key=True)
    note_id: Mapped[int] = mapped_column(ForeignKey("note.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    content: Mapped[str] = mapped_column(Text)
