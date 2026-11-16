from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_v1_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import create_db_engine, create_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application instance."""
    active_settings = settings or get_settings()
    configure_logging(active_settings.log_level)

    engine = create_db_engine(
        active_settings.database_url,
        echo=active_settings.db_echo,
    )
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(application: FastAPI):  # type: ignore[no-untyped-def]
        application.state.settings = active_settings
        application.state.engine = engine
        application.state.session_factory = session_factory
        try:
            yield
        finally:
            engine.dispose()

    application = FastAPI(
        title=active_settings.app_name,
        version="0.1.0",
        docs_url="/docs" if active_settings.app_env != "production" else None,
        redoc_url="/redoc" if active_settings.app_env != "production" else None,
        lifespan=lifespan,
    )
    application.state.settings = active_settings
    application.state.engine = engine
    application.state.session_factory = session_factory

    application.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )

    application.include_router(api_v1_router, prefix=active_settings.api_v1_prefix)
    return application


def __getattr__(name: str) -> Any:
    """Lazily build default ASGI app on attribute lookup (e.g. uvicorn app.main:app)."""
    if name == "app":
        return create_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
