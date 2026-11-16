from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app

TEST_DB_URL = "postgresql+psycopg://postgres:supersecret_pass@localhost:5432/norus_billwise_test"
TEST_JWT_SECRET = "test-only-signing-key-with-at-least-32-characters"


@pytest.fixture
def test_settings() -> Settings:
    """Return isolated test settings without reading local .env secrets."""
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=TEST_DB_URL,
        jwt_secret_key=TEST_JWT_SECRET,
        cookie_secure=False,
        cors_origins=["http://localhost:3000"],
        log_level="WARNING",
    )


@pytest.fixture
def client(test_settings: Settings) -> Generator[TestClient, None, None]:
    """Provide an isolated FastAPI TestClient per test."""
    get_settings.cache_clear()
    application = create_app(test_settings)
    with TestClient(application) as test_client:
        yield test_client
    application.dependency_overrides.clear()
    get_settings.cache_clear()
