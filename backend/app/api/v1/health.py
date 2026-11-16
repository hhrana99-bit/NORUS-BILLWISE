from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import get_db
from app.schemas.base import HealthResponse, ReadyResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    response_model_by_alias=True,
    summary="Application liveness check",
)
def health_check(request: Request) -> HealthResponse:
    """Confirm the FastAPI process is running without touching external services."""
    settings: Settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        service="norus-billwise-api",
        environment=settings.app_env,
    )


@router.get(
    "/ready",
    response_model=ReadyResponse,
    response_model_by_alias=True,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadyResponse}},
    summary="Database readiness check",
)
def readiness_check(db: Session = Depends(get_db)) -> ReadyResponse | JSONResponse:
    """Verify PostgreSQL connectivity via SELECT 1 without leaking credentials or traces."""
    try:
        db.execute(text("SELECT 1"))
        return ReadyResponse(status="ready", database="connected")
    except (SQLAlchemyError, OSError):
        logger.warning("Readiness check failed: database unreachable.")
        payload = ReadyResponse(
            status="unavailable",
            database="unreachable",
            detail="Database readiness check failed.",
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=payload.model_dump(by_alias=True),
        )
