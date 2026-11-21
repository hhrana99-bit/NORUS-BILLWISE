from __future__ import annotations

import re
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.v1 import api_v1_router
from app.core.config import Settings, get_settings
from app.core.errors import AppError, build_error_response, register_exception_handlers
from app.core.logging import configure_logging
from app.db.session import create_db_engine, create_session_factory
from app.services.storage_service import MAX_DOCUMENT_UPLOAD_REQUEST_BYTES

UPLOAD_SIZE_LIMIT_MESSAGE = (
    "Document upload request body exceeds the 16 MiB maximum request size "
    "(15 MB file limit plus 1 MiB multipart overhead)."
)


class _UploadSizeExceededError(AppError):
    """Internal ASGI control-flow AppError raised when streamed upload body crosses limit."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            code="FILE_TOO_LARGE",
            message=UPLOAD_SIZE_LIMIT_MESSAGE,
        )


class RequestIdMiddleware:
    """Pure ASGI middleware attaching a per-request ID to scope.state and X-Request-ID header."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = f"req_{uuid.uuid4().hex[:16]}"
        scope_state = scope.setdefault("state", {})
        if isinstance(scope_state, dict):
            scope_state["request_id"] = request_id

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                raw_headers = list(message.get("headers", []))
                has_header = any(
                    name.lower() == b"x-request-id" for name, _ in raw_headers
                )
                if not has_header:
                    raw_headers.append((b"x-request-id", request_id.encode("ascii")))
                    message = {**message, "headers": raw_headers}
            await send(message)

        await self.app(scope, receive, send_with_request_id)


class DocumentUploadSizeLimitMiddleware:
    """Enforce request-body size limit on workspace document uploads before multipart parsing."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        api_v1_prefix: str = "/api/v1",
        max_request_bytes: int = MAX_DOCUMENT_UPLOAD_REQUEST_BYTES,
    ) -> None:
        self.app = app
        prefix = api_v1_prefix.rstrip("/") or "/api/v1"
        self._upload_path_re = re.compile(
            rf"^{re.escape(prefix)}/workspaces/[^/]+/documents$"
        )
        self.max_request_bytes = max_request_bytes

    def _matches_upload_route(self, scope: Scope) -> bool:
        if scope["type"] != "http":
            return False
        if scope.get("method", "").upper() != "POST":
            return False
        path = scope.get("path", "")
        return bool(self._upload_path_re.match(path))

    @staticmethod
    def _extract_content_lengths(scope: Scope) -> list[int]:
        lengths: list[int] = []
        for name, value in scope.get("headers", []):
            if name.lower() == b"content-length":
                parsed = int(value.decode("ascii").strip())
                if parsed < 0:
                    raise ValueError("Negative Content-Length")
                lengths.append(parsed)
        return lengths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._matches_upload_route(scope):
            await self.app(scope, receive, send)
            return

        scope_state = scope.get("state")
        request_id = (
            scope_state.get("request_id") if isinstance(scope_state, dict) else None
        )

        try:
            content_lengths = self._extract_content_lengths(scope)
        except (UnicodeDecodeError, ValueError):
            response = build_error_response(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="VALIDATION_ERROR",
                message="Invalid Content-Length header.",
                request_id=request_id,
            )
            await response(scope, receive, send)
            return

        if content_lengths and (
            len(set(content_lengths)) > 1
            or any(length > self.max_request_bytes for length in content_lengths)
        ):
            if len(set(content_lengths)) > 1:
                response = build_error_response(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code="VALIDATION_ERROR",
                    message="Conflicting Content-Length headers.",
                    request_id=request_id,
                )
            else:
                response = build_error_response(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    code="FILE_TOO_LARGE",
                    message=UPLOAD_SIZE_LIMIT_MESSAGE,
                    request_id=request_id,
                )
            await response(scope, receive, send)
            return

        bytes_received = 0
        limit_exceeded = False
        response_started = False
        suppress_inner_error = False

        async def counting_receive() -> Message:
            nonlocal bytes_received, limit_exceeded
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                bytes_received += len(chunk)
                if bytes_received > self.max_request_bytes:
                    limit_exceeded = True
                    raise _UploadSizeExceededError()
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started, suppress_inner_error
            if message["type"] == "http.response.start":
                if limit_exceeded and not response_started and message.get("status") != 413:
                    suppress_inner_error = True
                    return
                response_started = True
                await send(message)
                return

            if suppress_inner_error:
                return
            await send(message)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except _UploadSizeExceededError:
            pass

        if limit_exceeded and not response_started:
            response = build_error_response(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                code="FILE_TOO_LARGE",
                message=UPLOAD_SIZE_LIMIT_MESSAGE,
                request_id=request_id,
            )
            await response(scope, receive, send)


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

    register_exception_handlers(application)
    application.include_router(api_v1_router, prefix=active_settings.api_v1_prefix)

    # Middleware execution order (outermost added last):
    # CORSMiddleware -> RequestIdMiddleware -> DocumentUploadSizeLimitMiddleware -> router
    application.add_middleware(
        DocumentUploadSizeLimitMiddleware,
        api_v1_prefix=active_settings.api_v1_prefix,
        max_request_bytes=MAX_DOCUMENT_UPLOAD_REQUEST_BYTES,
    )
    application.add_middleware(RequestIdMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )
    return application


def __getattr__(name: str) -> Any:
    """Lazily build default ASGI app on attribute lookup (e.g. uvicorn app.main:app)."""
    if name == "app":
        return create_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
