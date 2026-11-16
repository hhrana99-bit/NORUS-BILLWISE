from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401 - register all ORM models on Base.metadata
from app.core.config import get_settings
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


DEFAULT_ALEMBIC_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/norus_billwise"


def _resolve_database_url() -> str:
    """Resolve database URL from `-x db_url=...`, explicit Alembic config, env, or Settings."""
    x_args = context.get_x_argument(as_dictionary=True)
    if x_args.get("db_url"):
        return str(x_args["db_url"])

    configured_url = config.get_main_option("sqlalchemy.url")
    # Respect explicit programmatic overrides (e.g., TEST_DATABASE_URL in pytest)
    # before falling back to ambient DATABASE_URL / .env settings.
    if configured_url and configured_url != DEFAULT_ALEMBIC_URL:
        return configured_url

    env_db_url = os.environ.get("DATABASE_URL")
    if env_db_url:
        return env_db_url

    try:
        return get_settings().database_url
    except Exception:
        if configured_url:
            return configured_url
        raise


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode without a live DBAPI connection."""
    url = _resolve_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with a PostgreSQL connection."""
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _resolve_database_url()

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
