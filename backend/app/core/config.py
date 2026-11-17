from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration for NORUS BILLWISE backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "NORUS BILLWISE API"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    api_v1_prefix: str = "/api/v1"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    database_url: str = Field(
        ...,
        description="PostgreSQL SQLAlchemy connection URL (postgresql+psycopg://...)",
    )
    jwt_secret_key: SecretStr = Field(
        ...,
        description="Signing secret for short-lived access cookies (min 32 chars).",
    )
    cookie_secure: bool = Field(
        default=True,
        description="Set Secure attribute on auth/CSRF cookies (required true in staging/production).",
    )
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        description="Explicit allowed browser origins; '*' is prohibited when credentials are enabled.",
    )
    document_storage_root: str = "./var/documents"
    db_echo: bool = False
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 14
    jwt_issuer: str = "norus-billwise-api"
    jwt_audience: str = "norus-billwise-app"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                parsed = json.loads(stripped)
                if not isinstance(parsed, list):
                    raise ValueError("CORS_ORIGINS JSON value must be a list of strings.")
                return [str(item).strip() for item in parsed if str(item).strip()]
            return [item.strip() for item in stripped.split(",") if item.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        raise ValueError("CORS_ORIGINS must be a comma-separated string or list of strings.")

    @model_validator(mode="after")
    def validate_security_and_database(self) -> Settings:
        db_url = self.database_url.strip()
        if not (
            db_url.startswith("postgresql+psycopg://")
            or db_url.startswith("postgresql://")
        ):
            raise ValueError(
                "DATABASE_URL must use PostgreSQL (postgresql+psycopg://... or postgresql://...)."
            )

        if not self.api_v1_prefix.startswith("/"):
            raise ValueError("API_V1_PREFIX must begin with '/'.")

        if self.access_token_expire_minutes < 1:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be at least 1.")

        if self.refresh_token_expire_days < 1:
            raise ValueError("REFRESH_TOKEN_EXPIRE_DAYS must be at least 1.")

        for origin in self.cors_origins:
            if origin.strip() == "*":
                raise ValueError(
                    "CORS_ORIGINS cannot include wildcard '*' when cookie credentials are enabled."
                )

        secret_value = self.jwt_secret_key.get_secret_value().strip()
        if len(secret_value) < 32:
            raise ValueError(
                "JWT_SECRET_KEY must be at least 32 characters long."
            )

        if self.app_env in {"staging", "production"}:
            if not self.cookie_secure:
                raise ValueError(
                    "COOKIE_SECURE must be true in staging and production environments."
                )
            if "CHANGE_ME" in secret_value.upper():
                raise ValueError(
                    "JWT_SECRET_KEY cannot use a placeholder value in staging or production."
                )
            parsed = urlparse(db_url)
            if parsed.password and "CHANGE_ME" in parsed.password.upper():
                raise ValueError(
                    "DATABASE_URL cannot use a placeholder password in staging or production."
                )

        return self

    def redacted_database_target(self) -> str:
        """Return database host/name without exposing credentials."""
        parsed = urlparse(self.database_url)
        host = parsed.hostname or "unknown-host"
        port = f":{parsed.port}" if parsed.port else ""
        db_name = parsed.path.lstrip("/") or "unknown-db"
        return f"{parsed.scheme}://{host}{port}/{db_name}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached application settings loaded from environment / .env."""
    return Settings()  # type: ignore[call-arg]
