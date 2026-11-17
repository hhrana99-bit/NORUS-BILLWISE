from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

VALID_SECRET = "unit-test-secret-key-at-least-thirty-two-chars"


def test_settings_accepts_valid_postgresql_configuration() -> None:
    settings = Settings(
        _env_file=None,
        app_env="development",
        database_url="postgresql+psycopg://app_user:secret123@db.internal:5432/norus_billwise",
        jwt_secret_key=VALID_SECRET,
        cookie_secure=False,
        cors_origins=["http://localhost:3000"],
    )

    assert settings.app_name == "NORUS BILLWISE API"
    assert settings.api_v1_prefix == "/api/v1"
    redacted = settings.redacted_database_target()
    assert "secret123" not in redacted
    assert "app_user" not in redacted
    assert redacted == "postgresql+psycopg://db.internal:5432/norus_billwise"


@pytest.mark.parametrize(
    "bad_url",
    [
        "sqlite:///./local.db",
        "mysql+pymysql://user:pass@localhost/db",
        "http://localhost:5432/norus",
    ],
)
def test_settings_rejects_non_postgresql_database_url(bad_url: str) -> None:
    with pytest.raises(ValidationError, match="PostgreSQL"):
        Settings(
            _env_file=None,
            app_env="test",
            database_url=bad_url,
            jwt_secret_key=VALID_SECRET,
        )


def test_settings_rejects_short_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="32 characters"):
        Settings(
            _env_file=None,
            app_env="development",
            database_url="postgresql+psycopg://postgres:pass@localhost:5432/norus_billwise",
            jwt_secret_key="too-short",
        )


def test_settings_rejects_wildcard_cors_origin() -> None:
    with pytest.raises(ValidationError, match="wildcard"):
        Settings(
            _env_file=None,
            app_env="development",
            database_url="postgresql+psycopg://postgres:pass@localhost:5432/norus_billwise",
            jwt_secret_key=VALID_SECRET,
            cors_origins=["*"],
        )


def test_settings_enforces_cookie_secure_and_non_placeholder_secrets_in_production() -> None:
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        Settings(
            _env_file=None,
            app_env="production",
            database_url="postgresql+psycopg://postgres:realpass@localhost:5432/norus_billwise",
            jwt_secret_key=VALID_SECRET,
            cookie_secure=False,
        )

    with pytest.raises(ValidationError, match="placeholder"):
        Settings(
            _env_file=None,
            app_env="staging",
            database_url="postgresql+psycopg://postgres:realpass@localhost:5432/norus_billwise",
            jwt_secret_key="CHANGE_ME_WITH_A_SECURE_32_PLUS_CHAR_SECRET",
            cookie_secure=True,
        )


def test_settings_accepts_comma_separated_and_json_cors_origins_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:realpass@localhost:5432/norus_billwise",
    )
    monkeypatch.setenv("JWT_SECRET_KEY", VALID_SECRET)
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://localhost:3000, http://127.0.0.1:3000 ",
    )

    comma_settings = Settings(_env_file=None)
    assert comma_settings.cors_origins == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    monkeypatch.setenv(
        "CORS_ORIGINS",
        '["https://app.norusbillwise.example", "https://admin.norusbillwise.example"]',
    )
    json_settings = Settings(_env_file=None)
    assert json_settings.cors_origins == [
        "https://app.norusbillwise.example",
        "https://admin.norusbillwise.example",
    ]

    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000, *")
    with pytest.raises(ValidationError, match="wildcard"):
        Settings(_env_file=None)


def test_settings_accepts_direct_python_list_cors_origins_and_nodecode_import() -> None:
    from pydantic_settings import NoDecode

    assert NoDecode is not None

    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+psycopg://postgres:realpass@localhost:5432/norus_billwise_test",
        jwt_secret_key=VALID_SECRET,
        cookie_secure=False,
        cors_origins=[
            " http://localhost:3000 ",
            "https://portal.norusbillwise.example",
        ],
    )
    assert settings.cors_origins == [
        "http://localhost:3000",
        "https://portal.norusbillwise.example",
    ]


def test_settings_trusted_proxies_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:realpass@localhost:5432/norus_billwise_test",
    )
    monkeypatch.setenv("JWT_SECRET_KEY", VALID_SECRET)
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("TRUSTED_PROXIES", "127.0.0.1, 10.0.0.0/8")

    comma_settings = Settings(_env_file=None)
    assert comma_settings.trusted_proxies == ["127.0.0.1/32", "10.0.0.0/8"]

    monkeypatch.setenv("TRUSTED_PROXIES", '["192.168.10.5", "fd00::/8"]')
    json_settings = Settings(_env_file=None)
    assert json_settings.trusted_proxies == ["192.168.10.5/32", "fd00::/8"]

    for bad_proxy in ("*", "0.0.0.0/0", "::/0", "not-an-ip-address"):
        monkeypatch.setenv("TRUSTED_PROXIES", bad_proxy)
        with pytest.raises(ValidationError):
            Settings(_env_file=None)
