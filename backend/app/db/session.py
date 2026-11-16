from __future__ import annotations

from collections.abc import Generator

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_db_engine(database_url: str, *, echo: bool = False) -> Engine:
    """Build a PostgreSQL SQLAlchemy 2.0 engine with pre-ping enabled."""
    return create_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
        future=True,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory configured for explicit commit control."""
    return sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )


def get_db(request: Request) -> Generator[Session, None, None]:
    """FastAPI dependency yielding an isolated database session per request."""
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
