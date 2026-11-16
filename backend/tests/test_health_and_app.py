from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_db


class _HealthySession:
    def execute(self, statement: Any) -> int:
        return 1


class _BrokenSession:
    def execute(self, statement: Any) -> Any:
        raise OperationalError(
            "SELECT 1",
            {},
            Exception("FATAL: password authentication failed for supersecret_pass"),
        )


def test_health_endpoint_returns_liveness_payload(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "norus-billwise-api",
        "environment": "test",
    }


def test_ready_endpoint_returns_200_when_database_reachable(client: TestClient) -> None:
    client.app.dependency_overrides[get_db] = lambda: _HealthySession()

    response = client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "connected",
        "detail": None,
    }


def test_ready_endpoint_returns_503_without_leaking_credentials(
    client: TestClient,
) -> None:
    client.app.dependency_overrides[get_db] = lambda: _BrokenSession()

    response = client.get("/api/v1/ready")

    assert response.status_code == 503
    body = response.json()
    assert body == {
        "status": "unavailable",
        "database": "unreachable",
        "detail": "Database readiness check failed.",
    }
    raw_text = response.text
    assert "supersecret_pass" not in raw_text
    assert "password authentication failed" not in raw_text
