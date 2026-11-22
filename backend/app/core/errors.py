from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.schemas.base import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Domain or security exception mapped to the standard camelCase error envelope."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        clear_auth_cookies: bool = False,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.clear_auth_cookies = clear_auth_cookies
        self.headers = headers


def get_request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def build_error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    envelope = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            details=details,
            request_id=request_id,
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(by_alias=True, exclude_none=True),
        headers=headers,
    )


def register_exception_handlers(application: FastAPI) -> None:
    """Attach standard camelCase API error handlers without leaking secrets or stack traces."""

    @application.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        response = build_error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
            request_id=get_request_id(request),
            headers=exc.headers,
        )
        if exc.clear_auth_cookies:
            from app.core.cookies import clear_auth_cookies

            settings = request.app.state.settings
            clear_auth_cookies(response, settings)
        return response

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        safe_errors = [
            {
                "loc": [str(part) for part in err.get("loc", ())],
                "msg": str(err.get("msg", "Invalid input")),
                "type": str(err.get("type", "value_error")),
            }
            for err in exc.errors()
        ]
        # Preserve specific contract error codes raised inside Pydantic field validators
        error_code = "VALIDATION_ERROR"
        message = "Request validation failed."
        contract_markers = (
            ("HUMAN_REVIEW_CANNOT_BE_DISABLED", "requireHumanReview cannot be disabled."),
            ("EMPTY_FLAG_REASON", "reasonText cannot be blank."),
            ("INVALID_FLAG_RESOLUTION", "resolutionNote cannot be blank."),
            ("REOPEN_REASON_REQUIRED", "reason cannot be blank."),
        )
        for err in exc.errors():
            err_msg = str(err.get("msg", ""))
            matched = False
            for marker, marker_msg in contract_markers:
                if marker in err_msg:
                    error_code = marker
                    message = marker_msg
                    matched = True
                    break
            if matched:
                break

        return build_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code=error_code,
            message=message,
            details={"errors": safe_errors},
            request_id=get_request_id(request),
        )

    @application.exception_handler(SQLAlchemyError)
    async def handle_sqlalchemy_error(
        request: Request, exc: SQLAlchemyError
    ) -> JSONResponse:
        request_id = get_request_id(request)
        logger.error(
            "Unhandled database exception on request_id=%s type=%s",
            request_id,
            type(exc).__name__,
        )
        return build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_ERROR",
            message="An unexpected internal error occurred.",
            request_id=request_id,
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request, exc: Exception
    ) -> JSONResponse:
        request_id = get_request_id(request)
        logger.error(
            "Unhandled application exception on request_id=%s type=%s",
            request_id,
            type(exc).__name__,
        )
        return build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_ERROR",
            message="An unexpected internal error occurred.",
            request_id=request_id,
        )
