from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas.base import ErrorDetail, ErrorResponse


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
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.clear_auth_cookies = clear_auth_cookies


def get_request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def build_error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
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
        # Preserve specific contract error code when requireHumanReview=false is rejected
        error_code = "VALIDATION_ERROR"
        message = "Request validation failed."
        for err in exc.errors():
            err_msg = str(err.get("msg", ""))
            if "HUMAN_REVIEW_CANNOT_BE_DISABLED" in err_msg:
                error_code = "HUMAN_REVIEW_CANNOT_BE_DISABLED"
                message = "requireHumanReview cannot be disabled."
                break

        return build_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code=error_code,
            message=message,
            details={"errors": safe_errors},
            request_id=get_request_id(request),
        )
