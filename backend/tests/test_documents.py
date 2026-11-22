from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import uuid
from collections.abc import Callable, Generator
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.cookies import CSRF_COOKIE_NAME
from app.core.errors import AppError
from app.main import DocumentUploadSizeLimitMiddleware, create_app
from app.models.accounting import Document, Invoice
from app.models.review import AuditEvent
from app.schemas.documents import DocumentDto, DocumentUploadResponse
from app.services.document_service import (
    _clean_optional_text,
    build_content_disposition,
    get_clean_document_stream,
    upload_workspace_document,
)
from app.services.storage_service import (
    MAX_DOCUMENT_BYTES,
    MAX_DOCUMENT_UPLOAD_REQUEST_BYTES,
    MAX_MULTIPART_OVERHEAD_BYTES,
    STREAM_CHUNK_SIZE,
    LocalFilesystemStorage,
    build_workspace_document_storage_key,
    sanitize_original_filename,
    validate_declared_upload_type,
    verify_magic_bytes_match_format,
)
from tests.conftest import TEST_DB_URL, TEST_JWT_SECRET
from tests.test_migrations import (
    ALLOWED_POSTGRES_SCHEMES,
    APPROVED_TEST_HOSTS,
    REQUIRED_TEST_DATABASE_NAME,
    MigrationTestSafetyError,
)


class _TrackingChunkedStream:
    """Custom BinaryIO-like reader tracking chunk read sizes and total bytes read."""

    def __init__(self, header: bytes, body_byte: bytes, total_size: int) -> None:
        self._header = header
        self._body_byte = body_byte
        self._total_size = total_size
        self._pos = 0
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if self._pos >= self._total_size:
            return b""
        to_read = self._total_size - self._pos if size < 0 else min(size, self._total_size - self._pos)
        out = bytearray()
        if self._pos < len(self._header):
            take_header = min(to_read, len(self._header) - self._pos)
            out.extend(self._header[self._pos : self._pos + take_header])
            self._pos += take_header
            to_read -= take_header
        if to_read > 0:
            out.extend(self._body_byte * to_read)
            self._pos += to_read
        return bytes(out)

    @property
    def bytes_read(self) -> int:
        return self._pos


def _pdf_bytes(size: int = 256) -> bytes:
    prefix = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
    if size <= len(prefix):
        return prefix[:size]
    return prefix + (b"0" * (size - len(prefix)))


def _png_bytes(size: int = 128) -> bytes:
    prefix = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    if size <= len(prefix):
        return prefix[:size]
    return prefix + (b"\x00" * (size - len(prefix)))


def _jpeg_bytes(size: int = 128) -> bytes:
    prefix = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00"
    if size <= len(prefix):
        return prefix[:size]
    return prefix + (b"\xff\xd9" * ((size - len(prefix) + 1) // 2))[: size - len(prefix)]


def _webp_bytes(size: int = 128) -> bytes:
    prefix = b"RIFF\x24\x00\x00\x00WEBPVP8 \x18\x00\x00\x00"
    if size <= len(prefix):
        return prefix[:size]
    return prefix + (b"\x00" * (size - len(prefix)))


# ---------------------------------------------------------------------------
# Offline unit tests (run even without PostgreSQL)
# ---------------------------------------------------------------------------


def test_settings_rejects_blank_document_storage_root() -> None:
    with pytest.raises(
        ValidationError,
        match=r"(?i)DOCUMENT_STORAGE_ROOT cannot be blank\.",
    ):
        Settings(
            _env_file=None,
            app_env="test",
            database_url=TEST_DB_URL,
            jwt_secret_key=TEST_JWT_SECRET,
            document_storage_root="   \t  ",
        )


def test_filename_sanitization_and_content_disposition_safety() -> None:
    assert sanitize_original_filename("../../etc/passwd.pdf") == "passwd.pdf"
    assert (
        sanitize_original_filename(r"C:\Users\Finance\..\Tax\inv_01.pdf")
        == "inv_01.pdf"
    )
    cleaned = sanitize_original_filename('inv\r\n;filename="evil"\x00.pdf')
    assert "\r" not in cleaned
    assert "\n" not in cleaned
    assert ";" not in cleaned
    assert '"' not in cleaned
    assert "\x00" not in cleaned
    assert cleaned.endswith(".pdf")

    long_name = ("a" * 300) + ".pdf"
    bounded = sanitize_original_filename(long_name)
    assert len(bounded) == 255
    assert bounded.endswith(".pdf")

    assert sanitize_original_filename("...", fallback_ext=".pdf") == "document.pdf"
    assert sanitize_original_filename('vendor\r\n"report".pdf') == "vendor_report_.pdf"
    assert (
        build_content_disposition(
            original_filename='vendor\r\n"report".pdf', download=False
        )
        == 'inline; filename="vendor_report_.pdf"'
    )
    assert (
        build_content_disposition(original_filename="invoice.pdf", download=True)
        == 'attachment; filename="invoice.pdf"'
    )


def test_document_dto_never_exposes_storage_key() -> None:
    now = datetime.now(timezone.utc)
    fake_doc = SimpleNamespace(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        uploaded_by_user_id=uuid.uuid4(),
        original_filename="vendor-invoice.pdf",
        storage_key="orgs/secret/path/doc.pdf",
        mime_type="application/pdf",
        byte_size=1024,
        sha256_checksum="a" * 64,
        page_count=1,
        scan_status="PENDING",
        created_at=now,
    )
    dto = DocumentDto.model_validate(fake_doc)
    resp = DocumentUploadResponse(document=dto, invoice_id=uuid.uuid4())
    dumped = resp.model_dump(by_alias=True)
    assert "storageKey" not in dumped["document"]
    assert "storage_key" not in dumped["document"]
    assert "orgs/secret" not in str(dumped)


def test_declared_type_and_magic_bytes_validation() -> None:
    for fname, mime, sample in (
        ("a.pdf", "application/pdf", _pdf_bytes()),
        ("b.png", "image/png; charset=binary", _png_bytes()),
        ("c.jpg", "image/jpeg", _jpeg_bytes()),
        ("d.jpeg", "image/jpg", _jpeg_bytes()),
        ("e.webp", "image/webp", _webp_bytes()),
    ):
        spec, safe = validate_declared_upload_type(
            raw_filename=fname,
            declared_content_type=mime,
        )
        assert safe == fname
        verify_magic_bytes_match_format(sample[:16], spec)

    # Unsupported extensions
    for bad_name, bad_mime in (
        ("payload.svg", "image/svg+xml"),
        ("payload.exe", "application/octet-stream"),
        ("payload.html", "text/html"),
        ("noext", "application/pdf"),
    ):
        with pytest.raises(AppError) as exc_info:
            validate_declared_upload_type(
                raw_filename=bad_name, declared_content_type=bad_mime
            )
        assert exc_info.value.status_code == 415
        assert exc_info.value.code == "UNSUPPORTED_MEDIA_TYPE"

    # Extension / MIME mismatch
    with pytest.raises(AppError) as mismatch_exc:
        validate_declared_upload_type(
            raw_filename="invoice.pdf", declared_content_type="image/png"
        )
    assert mismatch_exc.value.status_code == 415

    # Spoofed magic bytes (PDF extension + MIME, PNG/HTML/PE payload)
    pdf_spec, _ = validate_declared_upload_type(
        raw_filename="invoice.pdf", declared_content_type="application/pdf"
    )
    for spoof in (b"<script>alert(1)</script>", _png_bytes(), b"MZ\x90\x00" + b"0" * 12):
        with pytest.raises(AppError) as magic_exc:
            verify_magic_bytes_match_format(spoof[:16], pdf_spec)
        assert magic_exc.value.status_code == 415
        assert magic_exc.value.code == "UNSUPPORTED_MEDIA_TYPE"

    # Spoofed WEBP (RIFF header without WEBP marker)
    webp_spec, _ = validate_declared_upload_type(
        raw_filename="scan.webp", declared_content_type="image/webp"
    )
    with pytest.raises(AppError) as riff_exc:
        verify_magic_bytes_match_format(b"RIFF\x24\x00\x00\x00AVI \x00\x00\x00\x00", webp_spec)
    assert riff_exc.value.status_code == 415


def test_local_filesystem_storage_containment_streaming_limits_and_cleanup(
    tmp_path: Path,
) -> None:
    root = tmp_path / "storage_root"
    storage = LocalFilesystemStorage(root)
    assert storage.root == root.resolve()

    # Path traversal & unsafe storage_key rejections
    for bad_key in (
        "",
        "../escape.pdf",
        "orgs/../escape.pdf",
        "/abs/path.pdf",
        r"orgs\backslash.pdf",
        "C:/drive.pdf",
        "orgs/null\x00byte.pdf",
        "./dot.pdf",
    ):
        with pytest.raises(AppError) as key_exc:
            storage.save_stream(storage_key=bad_key, stream=io.BytesIO(_pdf_bytes()))
        assert key_exc.value.code == "STORAGE_PATH_INVALID"
        assert key_exc.value.status_code == 500

    # Symlink escape containment check
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    root.mkdir(parents=True, exist_ok=True)
    symlink_dir = root / "orgs"
    try:
        os.symlink(outside_dir, symlink_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        pass
    else:
        with pytest.raises(AppError) as sym_exc:
            storage.save_stream(
                storage_key="orgs/escape/doc.pdf",
                stream=io.BytesIO(_pdf_bytes()),
            )
        assert sym_exc.value.code == "STORAGE_PATH_INVALID"
        symlink_dir.unlink()

    # Exact 15 MB boundary succeeds using <= 64 KB chunks
    org_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    key = build_workspace_document_storage_key(
        organization_id=org_id,
        workspace_id=ws_id,
        document_id=doc_id,
        canonical_ext=".pdf",
    )
    ok_stream = _TrackingChunkedStream(b"%PDF-1.7\n", b"A", MAX_DOCUMENT_BYTES)
    spec, _ = validate_declared_upload_type(
        raw_filename="exact_max.pdf", declared_content_type="application/pdf"
    )
    stored = storage.save_stream(
        storage_key=key,
        stream=ok_stream,
        header_validator=lambda hdr: verify_magic_bytes_match_format(hdr, spec),
    )
    assert stored.byte_size == MAX_DOCUMENT_BYTES
    assert all(1 <= s <= STREAM_CHUNK_SIZE for s in ok_stream.read_sizes)

    streamed_chunks = list(storage.open_stream(key))
    assert all(len(c) <= STREAM_CHUNK_SIZE for c in streamed_chunks)
    assert sum(len(c) for c in streamed_chunks) == MAX_DOCUMENT_BYTES
    storage.delete(key)
    with pytest.raises(AppError) as missing_exc:
        storage.open_stream(key)
    assert missing_exc.value.status_code == 404
    assert missing_exc.value.code == "DOCUMENT_CONTENT_NOT_FOUND"

    # 15 MB + 1 byte aborts early without reading huge trailing stream or leaving .part files
    oversize_key = build_workspace_document_storage_key(
        organization_id=org_id,
        workspace_id=ws_id,
        document_id=uuid.uuid4(),
        canonical_ext=".pdf",
    )
    oversize_stream = _TrackingChunkedStream(
        b"%PDF-1.7\n", b"B", MAX_DOCUMENT_BYTES + (10 * 1024 * 1024)
    )
    with pytest.raises(AppError) as size_exc:
        storage.save_stream(
            storage_key=oversize_key,
            stream=oversize_stream,
            header_validator=lambda hdr: verify_magic_bytes_match_format(hdr, spec),
        )
    assert size_exc.value.status_code == 413
    assert size_exc.value.code == "FILE_TOO_LARGE"
    assert oversize_stream.bytes_read <= MAX_DOCUMENT_BYTES + STREAM_CHUNK_SIZE
    leftover_files = [p for p in root.rglob("*") if p.is_file()]
    assert leftover_files == []

    # Empty stream -> 422 EMPTY_FILE
    with pytest.raises(AppError) as empty_exc:
        storage.save_stream(storage_key=oversize_key, stream=io.BytesIO(b""))
    assert empty_exc.value.status_code == 422
    assert empty_exc.value.code == "EMPTY_FILE"


def test_get_clean_document_stream_blocks_all_non_clean_statuses(
    tmp_path: Path,
) -> None:
    root = tmp_path / "gate_storage"
    storage = LocalFilesystemStorage(root)
    ws_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    key = build_workspace_document_storage_key(
        organization_id=uuid.uuid4(),
        workspace_id=ws_id,
        document_id=doc_id,
        canonical_ext=".pdf",
    )
    payload = _pdf_bytes(512)
    storage.save_stream(storage_key=key, stream=io.BytesIO(payload))

    class _StubSession:
        def __init__(self, doc: object | None) -> None:
            self._doc = doc

        def scalar(self, _stmt: object) -> object | None:
            return self._doc

    # Missing DB record -> 404
    with pytest.raises(AppError) as not_found_exc:
        get_clean_document_stream(
            _StubSession(None),  # type: ignore[arg-type]
            storage=storage,
            workspace_id=ws_id,
            document_id=doc_id,
        )
    assert not_found_exc.value.status_code == 404

    # All non-CLEAN statuses strictly blocked (never bypass SKIPPED_DEV, PENDING, or FAILED)
    for blocked_status in ("PENDING", "SKIPPED_DEV", "FAILED"):
        doc = SimpleNamespace(
            id=doc_id,
            workspace_id=ws_id,
            storage_key=key,
            scan_status=blocked_status,
        )
        with pytest.raises(AppError) as blocked_exc:
            get_clean_document_stream(
                _StubSession(doc),  # type: ignore[arg-type]
                storage=storage,
                workspace_id=ws_id,
                document_id=doc_id,
            )
        assert blocked_exc.value.status_code == 409
        assert blocked_exc.value.code == "DOCUMENT_SCAN_NOT_CLEAN"

    # INFECTED -> 403
    infected_doc = SimpleNamespace(
        id=doc_id,
        workspace_id=ws_id,
        storage_key=key,
        scan_status="INFECTED",
    )
    with pytest.raises(AppError) as inf_exc:
        get_clean_document_stream(
            _StubSession(infected_doc),  # type: ignore[arg-type]
            storage=storage,
            workspace_id=ws_id,
            document_id=doc_id,
        )
    assert inf_exc.value.status_code == 403
    assert inf_exc.value.code == "DOCUMENT_INFECTED"

    # Explicit CLEAN -> streams exact bytes
    clean_doc = SimpleNamespace(
        id=doc_id,
        workspace_id=ws_id,
        storage_key=key,
        scan_status="CLEAN",
    )
    returned_doc, stream = get_clean_document_stream(
        _StubSession(clean_doc),  # type: ignore[arg-type]
        storage=storage,
        workspace_id=ws_id,
        document_id=doc_id,
    )
    assert returned_doc.id == doc_id
    assert b"".join(stream) == payload


def test_clean_optional_text_and_upload_reject_nul_bytes_before_storage(
    tmp_path: Path,
) -> None:
    assert _clean_optional_text(None, max_len=240) is None
    assert _clean_optional_text("   \t\n  ", max_len=240) is None
    assert (
        _clean_optional_text("  Acme   Enterprises \n Pvt Ltd ", max_len=240)
        == "Acme Enterprises Pvt Ltd"
    )
    assert len(_clean_optional_text("A" * 300, max_len=240) or "") == 240

    for bad_val in ("Acme\x00Corp", "   \x00   ", "INV-01\x00"):
        with pytest.raises(AppError) as nul_exc:
            _clean_optional_text(bad_val, max_len=240, field_label="supplierName")
        assert nul_exc.value.status_code == 422
        assert nul_exc.value.code == "VALIDATION_ERROR"

    storage_root = tmp_path / "nul_guard_storage"
    storage = LocalFilesystemStorage(storage_root)
    dummy_ws = SimpleNamespace(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        name="Workspace",
    )
    dummy_actor = SimpleNamespace(id=uuid.uuid4(), full_name="Uploader")

    class _NoDbSession:
        def add(self, _obj: object) -> None:
            raise AssertionError("DB should not be touched on NUL validation error")

    for kwargs in (
        {"supplier_name": "Acme\x00Supplies"},
        {"invoice_number": "INV\x002026"},
        {"supplier_name": "Acme\x00Supplies", "create_draft_invoice": False},
    ):
        with pytest.raises(AppError) as up_exc:
            upload_workspace_document(
                _NoDbSession(),  # type: ignore[arg-type]
                storage=storage,
                workspace=dummy_ws,  # type: ignore[arg-type]
                actor=dummy_actor,  # type: ignore[arg-type]
                raw_filename="invoice.pdf",
                declared_content_type="application/pdf",
                file_stream=io.BytesIO(_pdf_bytes()),
                **kwargs,  # type: ignore[arg-type]
            )
        assert up_exc.value.status_code == 422
        assert up_exc.value.code == "VALIDATION_ERROR"
        assert list(storage_root.rglob("*")) == []


def test_asgi_upload_size_limit_middleware_pre_multipart_and_chunked_streaming() -> None:
    assert MAX_DOCUMENT_UPLOAD_REQUEST_BYTES == (
        MAX_DOCUMENT_BYTES + MAX_MULTIPART_OVERHEAD_BYTES
    )

    ws_id = uuid.uuid4()
    upload_path = f"/api/v1/workspaces/{ws_id}/documents"

    async def _run() -> None:
        inner_calls = 0

        async def _inner_app(scope: object, receive: object, send: object) -> None:
            nonlocal inner_calls
            inner_calls += 1
            while True:
                msg = await receive()  # type: ignore[misc]
                if msg["type"] == "http.request" and not msg.get("more_body", False):
                    break
            await send(  # type: ignore[misc]
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send(  # type: ignore[misc]
                {"type": "http.response.body", "body": b'{"ok":true}', "more_body": False}
            )

        middleware = DocumentUploadSizeLimitMiddleware(
            _inner_app,
            api_v1_prefix="/api/v1",
            max_request_bytes=1024,
        )

        # 1. Oversized Content-Length rejected before inner app or receive() is ever called
        sent_cl: list[dict[str, object]] = []
        cl_reads = 0

        async def _cl_receive() -> dict[str, object]:
            nonlocal cl_reads
            cl_reads += 1
            return {"type": "http.request", "body": b"ignored", "more_body": False}

        async def _cl_send(msg: dict[str, object]) -> None:
            sent_cl.append(msg)

        await middleware(
            {
                "type": "http",
                "method": "POST",
                "path": upload_path,
                "headers": [(b"content-length", b"1025")],
                "state": {"request_id": "req_cl_test"},
            },
            _cl_receive,
            _cl_send,  # type: ignore[arg-type]
        )
        assert inner_calls == 0
        assert cl_reads == 0
        starts = [m for m in sent_cl if m["type"] == "http.response.start"]
        bodies = [m for m in sent_cl if m["type"] == "http.response.body"]
        assert len(starts) == 1
        assert starts[0]["status"] == 413
        assert len(bodies) == 1
        err_payload = json.loads(bodies[0]["body"].decode("utf-8"))  # type: ignore[union-attr]
        assert err_payload["error"]["code"] == "FILE_TOO_LARGE"
        assert err_payload["error"]["requestId"] == "req_cl_test"

        # 2. Streamed request without Content-Length exceeding limit aborts early with 1 response
        sent_stream: list[dict[str, object]] = []
        chunks = [b"x" * 512, b"y" * 600, b"z" * 4096]
        chunk_idx = 0

        async def _stream_receive() -> dict[str, object]:
            nonlocal chunk_idx
            if chunk_idx >= len(chunks):
                return {"type": "http.request", "body": b"", "more_body": False}
            data = chunks[chunk_idx]
            chunk_idx += 1
            return {
                "type": "http.request",
                "body": data,
                "more_body": chunk_idx < len(chunks),
            }

        async def _stream_send(msg: dict[str, object]) -> None:
            sent_stream.append(msg)

        await middleware(
            {
                "type": "http",
                "method": "POST",
                "path": upload_path,
                "headers": [],
                "state": {"request_id": "req_stream_test"},
            },
            _stream_receive,
            _stream_send,  # type: ignore[arg-type]
        )
        # Aborted on chunk 2 (1112 > 1024), never pulled chunk 3
        assert chunk_idx == 2
        stream_starts = [m for m in sent_stream if m["type"] == "http.response.start"]
        stream_bodies = [m for m in sent_stream if m["type"] == "http.response.body"]
        assert len(stream_starts) == 1
        assert stream_starts[0]["status"] == 413
        assert len(stream_bodies) == 1
        stream_err = json.loads(stream_bodies[0]["body"].decode("utf-8"))  # type: ignore[union-attr]
        assert stream_err["error"]["code"] == "FILE_TOO_LARGE"
        assert stream_err["error"]["requestId"] == "req_stream_test"

        # 3. Other routes bypass limit completely even with larger body / Content-Length
        sent_other: list[dict[str, object]] = []
        other_chunks = [b"a" * 2048]
        other_idx = 0

        async def _other_receive() -> dict[str, object]:
            nonlocal other_idx
            if other_idx >= len(other_chunks):
                return {"type": "http.request", "body": b"", "more_body": False}
            data = other_chunks[other_idx]
            other_idx += 1
            return {"type": "http.request", "body": data, "more_body": False}

        async def _other_send(msg: dict[str, object]) -> None:
            sent_other.append(msg)

        await middleware(
            {
                "type": "http",
                "method": "POST",
                "path": f"/api/v1/workspaces/{ws_id}/suppliers",
                "headers": [(b"content-length", b"2048")],
                "state": {},
            },
            _other_receive,
            _other_send,  # type: ignore[arg-type]
        )
        assert inner_calls == 2
        assert sent_other[0]["status"] == 200

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# PostgreSQL 16 integration fixtures
# ---------------------------------------------------------------------------


def _validate_integration_postgres_url(
    raw_url: str | None, *, require_postgres: bool
) -> str | None:
    cleaned = (raw_url or "").strip()
    if not cleaned:
        if require_postgres:
            raise MigrationTestSafetyError(
                "TEST_DATABASE_URL is required when NORUS_REQUIRE_POSTGRES_TESTS=1."
            )
        return None

    parsed = urlparse(cleaned)
    if parsed.scheme.lower() not in ALLOWED_POSTGRES_SCHEMES:
        raise MigrationTestSafetyError(
            "TEST_DATABASE_URL must use postgresql:// or postgresql+psycopg://."
        )
    hostname = (parsed.hostname or "").lower()
    if hostname not in APPROVED_TEST_HOSTS:
        raise MigrationTestSafetyError(
            f"Refusing integration test DB connection on unapproved host {hostname!r}."
        )
    db_name = parsed.path.lstrip("/")
    if db_name != REQUIRED_TEST_DATABASE_NAME:
        raise MigrationTestSafetyError(
            f"Integration tests require database {REQUIRED_TEST_DATABASE_NAME!r}, got {db_name!r}."
        )
    return cleaned


@pytest.fixture(scope="module")
def pg_test_url() -> str:
    require_pg = os.environ.get("NORUS_REQUIRE_POSTGRES_TESTS", "").strip() == "1"
    raw_url = os.environ.get("TEST_DATABASE_URL", "")
    try:
        validated = _validate_integration_postgres_url(
            raw_url, require_postgres=require_pg
        )
    except MigrationTestSafetyError as exc:
        pytest.fail(str(exc), pytrace=False)

    if validated is None:
        pytest.skip(
            "TEST_DATABASE_URL is not set; skipping PostgreSQL documents integration tests."
        )

    from sqlalchemy import create_engine

    engine = create_engine(validated, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        engine.dispose()
        error_type = type(exc).__name__
        if require_pg:
            pytest.fail(
                f"PostgreSQL integration test failed: database unreachable ({error_type}) "
                "while NORUS_REQUIRE_POSTGRES_TESTS=1.",
                pytrace=False,
            )
        pytest.skip(f"PostgreSQL unavailable for integration tests ({error_type}).")

    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    alembic_cfg = Config(os.path.join(backend_dir, "alembic.ini"))
    alembic_cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", validated)
    command.upgrade(alembic_cfg, "head")
    engine.dispose()
    return validated


@pytest.fixture
def storage_root(tmp_path: Path) -> Path:
    root = tmp_path / "documents_root"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def pg_settings(pg_test_url: str, storage_root: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=pg_test_url,
        jwt_secret_key=TEST_JWT_SECRET,
        cookie_secure=False,
        cors_origins=["http://localhost:3000", "https://app.norus.example"],
        log_level="WARNING",
        access_token_expire_minutes=15,
        refresh_token_expire_days=14,
        document_storage_root=str(storage_root),
    )


@pytest.fixture
def db_session(pg_test_url: str) -> Generator[Session, None, None]:
    from sqlalchemy import create_engine

    engine = create_engine(pg_test_url, pool_pre_ping=True)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session
    engine.dispose()


@pytest.fixture
def make_client(
    pg_settings: Settings,
    pg_test_url: str,
) -> Generator[Callable[..., TestClient], None, None]:
    from sqlalchemy import create_engine

    clean_engine = create_engine(pg_test_url, pool_pre_ping=True)
    with clean_engine.begin() as conn:
        conn.execute(text("DELETE FROM auth_rate_limit_buckets"))
    clean_engine.dispose()

    stack = ExitStack()

    def _factory(
        *,
        custom_settings: Settings | None = None,
        base_url: str = "http://testserver",
        raise_server_exceptions: bool = True,
    ) -> TestClient:
        get_settings.cache_clear()
        app = create_app(custom_settings or pg_settings)
        client = stack.enter_context(
            TestClient(
                app,
                base_url=base_url,
                raise_server_exceptions=raise_server_exceptions,
            )
        )
        return client

    yield _factory
    stack.close()
    get_settings.cache_clear()


def _csrf_headers(client: TestClient, *, origin: str | None = None) -> dict[str, str]:
    token = client.cookies.get(CSRF_COOKIE_NAME)
    headers: dict[str, str] = {}
    if token:
        headers["X-CSRF-Token"] = token
    if origin:
        headers["Origin"] = origin
    return headers


def _register_user(
    client: TestClient,
    *,
    prefix: str,
    full_name: str = "CA Ananya Deshmukh",
    org_name: str | None = None,
    password: str = "StrongPractice!2026",
) -> dict:
    uid = uuid.uuid4().hex[:10]
    email = f"{prefix}.{uid}@example.invalid"
    payload: dict[str, object] = {
        "email": email,
        "password": password,
        "fullName": full_name,
    }
    if org_name is not None:
        payload["organizationName"] = org_name
        payload["firmType"] = "Chartered Accountancy Practice"

    resp = client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _onboard_to_workspace(
    admin_client: TestClient,
    *,
    org_id: str,
    workspace_id: str,
    member_client: TestClient,
    member_email: str,
    workspace_role: str,
) -> None:
    invite_resp = admin_client.post(
        f"/api/v1/organizations/{org_id}/invitations",
        headers=_csrf_headers(admin_client),
        json={"email": member_email, "role": "ORG_MEMBER"},
    )
    assert invite_resp.status_code == 201, invite_resp.text
    raw_token = invite_resp.json()["inviteToken"]

    accept_resp = member_client.post(
        "/api/v1/organizations/invitations/accept",
        headers=_csrf_headers(member_client),
        json={"token": raw_token},
    )
    assert accept_resp.status_code == 200, accept_resp.text

    mem_resp = admin_client.post(
        f"/api/v1/workspaces/{workspace_id}/memberships",
        headers=_csrf_headers(admin_client),
        json={"email": member_email, "role": workspace_role},
    )
    assert mem_resp.status_code == 201, mem_resp.text


# ---------------------------------------------------------------------------
# PostgreSQL 16 Documents Upload & Streaming integration tests
# ---------------------------------------------------------------------------


def test_document_upload_formats_draft_invoice_and_audit_event(
    make_client: Callable[..., TestClient],
    db_session: Session,
    storage_root: Path,
) -> None:
    client = make_client()
    uid = uuid.uuid4().hex[:8]
    reg = _register_user(client, prefix="doc_ok", org_name=f"Doc Firm {uid}")
    org_id = reg["organization"]["id"]
    ws_id = reg["workspace"]["workspaceId"]
    ws_uuid = uuid.UUID(ws_id)

    formats = [
        # Multi-chunk PDF (> 64 KB) + draft invoice created by default
        ("multi_chunk.pdf", "application/pdf", _pdf_bytes(160_000), True),
        ("scan.png", "image/png", _png_bytes(4096), False),
        ("photo.jpg", "image/jpeg", _jpeg_bytes(4096), False),
        ("receipt.webp", "image/webp", _webp_bytes(4096), False),
    ]

    for fname, mime, payload, create_draft in formats:
        resp = client.post(
            f"/api/v1/workspaces/{ws_id}/documents",
            headers=_csrf_headers(client),
            files={"file": (fname, payload, mime)},
            data={
                "supplierName": "Apex Components Pvt Ltd",
                "invoiceNumber": f"INV-{fname}",
                "createDraftInvoice": "true" if create_draft else "false",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        doc_json = body["document"]
        assert doc_json["originalFilename"] == fname
        assert doc_json["mimeType"] == mime
        assert doc_json["byteSize"] == len(payload)
        assert doc_json["sha256Checksum"] == hashlib.sha256(payload).hexdigest()
        assert doc_json["scanStatus"] == "PENDING"
        assert "storageKey" not in doc_json
        assert str(storage_root) not in resp.text

        doc_id = uuid.UUID(doc_json["id"])
        db_doc = db_session.get(Document, doc_id)
        assert db_doc is not None
        assert db_doc.workspace_id == ws_uuid
        assert db_doc.storage_key.startswith(f"orgs/{org_id}/workspaces/{ws_id}/")
        stored_path = storage_root / db_doc.storage_key
        assert stored_path.is_file()
        assert stored_path.read_bytes() == payload

        if create_draft:
            assert body["invoiceId"] is not None
            inv = db_session.get(Invoice, uuid.UUID(body["invoiceId"]))
            assert inv is not None
            assert inv.workspace_id == ws_uuid
            assert inv.document_id == doc_id
            assert inv.status == "PENDING_REVIEW"
            assert inv.source_type == "MANUAL_UPLOAD"
            assert inv.supplier_name_snapshot == "Apex Components Pvt Ltd"
            assert inv.invoice_number == f"INV-{fname}"
        else:
            assert body["invoiceId"] is None

    # Malicious client filename is sanitized cleanly without affecting UUID storage_key
    evil_pdf = _pdf_bytes(512)
    evil_resp = client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers=_csrf_headers(client),
        files={"file": ('../../etc/passwd\r\n"evil".pdf', evil_pdf, "application/pdf")},
    )
    assert evil_resp.status_code == 201, evil_resp.text
    evil_doc_json = evil_resp.json()["document"]
    assert ".." not in evil_doc_json["originalFilename"]
    assert "/" not in evil_doc_json["originalFilename"]
    assert "\r" not in evil_doc_json["originalFilename"]
    assert "\n" not in evil_doc_json["originalFilename"]
    assert '"' not in evil_doc_json["originalFilename"]
    assert evil_doc_json["originalFilename"].endswith(".pdf")

    evil_db = db_session.get(Document, uuid.UUID(evil_doc_json["id"]))
    assert evil_db is not None
    assert evil_db.storage_key.endswith(f"/{evil_doc_json['id']}.pdf")

    # Audit events logged for uploads without storage path exposure
    events = list(
        db_session.scalars(
            select(AuditEvent).where(
                AuditEvent.workspace_id == ws_uuid,
                AuditEvent.event_type == "document.uploaded",
            )
        )
    )
    assert len(events) == 5
    for ev in events:
        assert "storageKey" not in ev.event_metadata
        assert str(storage_root) not in ev.summary


def test_document_upload_rejects_spoofed_magic_oversize_and_empty_with_no_disk_leftovers(
    make_client: Callable[..., TestClient],
    db_session: Session,
    storage_root: Path,
) -> None:
    client = make_client()
    uid = uuid.uuid4().hex[:8]
    reg = _register_user(client, prefix="doc_val", org_name=f"Val Firm {uid}")
    ws_id = reg["workspace"]["workspaceId"]
    ws_uuid = uuid.UUID(ws_id)

    # 1. Extension not allowed (.svg)
    svg_resp = client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers=_csrf_headers(client),
        files={"file": ("scripted.svg", b"<svg><script>alert(1)</script></svg>", "image/svg+xml")},
    )
    assert svg_resp.status_code == 415
    assert svg_resp.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"

    # 2. Spoofed PDF extension + MIME with HTML/JS or PNG bytes
    spoof_resp = client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers=_csrf_headers(client),
        files={"file": ("fake.pdf", b"<script>alert(1)</script>", "application/pdf")},
    )
    assert spoof_resp.status_code == 415
    assert spoof_resp.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"

    spoof_png_as_pdf = client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers=_csrf_headers(client),
        files={"file": ("mismatch.pdf", _png_bytes(512), "application/pdf")},
    )
    assert spoof_png_as_pdf.status_code == 415

    # 3. Empty file -> 422 EMPTY_FILE
    empty_resp = client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers=_csrf_headers(client),
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert empty_resp.status_code == 422
    assert empty_resp.json()["error"]["code"] == "EMPTY_FILE"

    # 4. > 15 MB file -> 413 FILE_TOO_LARGE
    too_large_pdf = _pdf_bytes(MAX_DOCUMENT_BYTES + 1)
    big_resp = client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers=_csrf_headers(client),
        files={"file": ("too_big.pdf", too_large_pdf, "application/pdf")},
    )
    assert big_resp.status_code == 413
    assert big_resp.json()["error"]["code"] == "FILE_TOO_LARGE"

    # Zero files persisted on disk and zero DB Document/Invoice rows committed
    assert [p for p in storage_root.rglob("*") if p.is_file()] == []
    assert (
        list(db_session.scalars(select(Document).where(Document.workspace_id == ws_uuid)))
        == []
    )
    assert (
        list(db_session.scalars(select(Invoice).where(Invoice.workspace_id == ws_uuid)))
        == []
    )

    # 5. Embedded NUL bytes in supplierName or invoiceNumber -> 422 VALIDATION_ERROR cleanly
    for bad_field, bad_val in (
        ("supplierName", "Acme\x00Holdings"),
        ("invoiceNumber", "INV-\x00999"),
    ):
        nul_resp = client.post(
            f"/api/v1/workspaces/{ws_id}/documents",
            headers=_csrf_headers(client),
            files={"file": ("valid.pdf", _pdf_bytes(512), "application/pdf")},
            data={bad_field: bad_val},
        )
        assert nul_resp.status_code == 422, nul_resp.text
        assert nul_resp.json()["error"]["code"] == "VALIDATION_ERROR"

    assert [p for p in storage_root.rglob("*") if p.is_file()] == []


def test_document_upload_asgi_request_body_limit_before_multipart_parsing(
    make_client: Callable[..., TestClient],
    pg_settings: Settings,
    storage_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client()
    uid = uuid.uuid4().hex[:8]
    reg = _register_user(client, prefix="doc_asgi", org_name=f"ASGI Firm {uid}")
    ws_id = reg["workspace"]["workspaceId"]

    parser_invoked = False

    def _fail_if_reached(*_args: object, **_kwargs: object) -> object:
        nonlocal parser_invoked
        parser_invoked = True
        raise AssertionError("Multipart upload handler should not run on oversized request")

    monkeypatch.setattr(
        "app.api.v1.documents.upload_workspace_document",
        _fail_if_reached,
    )

    # 1. Oversized Content-Length rejected at ASGI layer before multipart parsing, preserving CORS & requestId
    csrf_headers = _csrf_headers(client, origin="http://localhost:3000")
    oversized_cl_resp = client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers={
            **csrf_headers,
            "Content-Type": "multipart/form-data; boundary=----boundary",
            "Content-Length": str(MAX_DOCUMENT_UPLOAD_REQUEST_BYTES + 1),
        },
        content=b"small",
    )
    assert oversized_cl_resp.status_code == 413
    assert oversized_cl_resp.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert oversized_cl_resp.json()["error"]["requestId"].startswith("req_")
    assert oversized_cl_resp.headers.get("x-request-id") == oversized_cl_resp.json()["error"]["requestId"]
    assert oversized_cl_resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert parser_invoked is False

    # 2. Streamed request without Content-Length exceeding 16 MiB against real create_app ASGI app
    app = create_app(pg_settings)
    chunk_size = 512 * 1024  # 512 KiB
    total_chunks = (MAX_DOCUMENT_UPLOAD_REQUEST_BYTES // chunk_size) + 4
    sent_messages: list[dict[str, object]] = []
    chunks_pulled = 0
    cookie_header = "; ".join(f"{k}={v}" for k, v in client.cookies.items()).encode("ascii")
    csrf_token_val = (client.cookies.get(CSRF_COOKIE_NAME) or "").encode("ascii")

    async def _run_chunked_asgi() -> None:
        async def _receive() -> dict[str, object]:
            nonlocal chunks_pulled
            if chunks_pulled >= total_chunks:
                return {"type": "http.request", "body": b"", "more_body": False}
            chunks_pulled += 1
            prefix = (
                b"--b\r\nContent-Disposition: form-data; name=\"file\"; filename=\"x.pdf\"\r\nContent-Type: application/pdf\r\n\r\n%PDF-1.7\n"
                if chunks_pulled == 1
                else b"0" * chunk_size
            )
            body = prefix.ljust(chunk_size, b"0")[:chunk_size]
            return {
                "type": "http.request",
                "body": body,
                "more_body": chunks_pulled < total_chunks,
            }

        async def _send(msg: dict[str, object]) -> None:
            sent_messages.append(msg)

        await app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": f"/api/v1/workspaces/{ws_id}/documents",
                "raw_path": f"/api/v1/workspaces/{ws_id}/documents".encode("ascii"),
                "query_string": b"",
                "headers": [
                    (b"host", b"testserver"),
                    (b"content-type", b"multipart/form-data; boundary=b"),
                    (b"origin", b"http://localhost:3000"),
                    (b"cookie", cookie_header),
                    (b"x-csrf-token", csrf_token_val),
                ],
                "client": ("127.0.0.1", 50000),
                "server": ("testserver", 80),
            },
            _receive,
            _send,  # type: ignore[arg-type]
        )

    try:
        asyncio.run(_run_chunked_asgi())
    finally:
        app.state.engine.dispose()
    starts = [m for m in sent_messages if m["type"] == "http.response.start"]
    bodies = [m for m in sent_messages if m["type"] == "http.response.body"]
    assert len(starts) == 1
    assert starts[0]["status"] == 413
    assert len(bodies) == 1
    err_json = json.loads(bodies[0]["body"].decode("utf-8"))  # type: ignore[union-attr]
    assert err_json["error"]["code"] == "FILE_TOO_LARGE"
    assert chunks_pulled < total_chunks
    assert parser_invoked is False

    # 3. Normal upload & other routes still function normally once monkeypatch is restored
    monkeypatch.undo()
    ok_resp = client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers=_csrf_headers(client),
        files={"file": ("within_limit.pdf", _pdf_bytes(4096), "application/pdf")},
        data={"supplierName": "Valid   Supplier ", "invoiceNumber": " INV-001 "},
    )
    assert ok_resp.status_code == 201, ok_resp.text

    supplier_resp = client.post(
        f"/api/v1/workspaces/{ws_id}/suppliers",
        headers=_csrf_headers(client),
        json={"name": "Unaffected Supplier Route"},
    )
    assert supplier_resp.status_code == 201, supplier_resp.text


def test_document_db_failure_triggers_storage_cleanup_and_rollback(
    make_client: Callable[..., TestClient],
    db_session: Session,
    storage_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client(raise_server_exceptions=False)
    uid = uuid.uuid4().hex[:8]
    reg = _register_user(client, prefix="doc_rb", org_name=f"Rollback Firm {uid}")
    ws_id = reg["workspace"]["workspaceId"]
    ws_uuid = uuid.UUID(ws_id)

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OperationalError(
            "INSERT INTO audit_events",
            {},
            Exception("simulated database failure during upload commit"),
        )

    monkeypatch.setattr("app.services.document_service.record_audit_event", _boom)

    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers=_csrf_headers(client),
        files={"file": ("rollback.pdf", _pdf_bytes(2048), "application/pdf")},
    )
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "INTERNAL_ERROR"
    assert str(storage_root) not in resp.text
    assert "simulated database failure" not in resp.text

    # Transaction rolled back AND blob deleted from storage_root
    assert [p for p in storage_root.rglob("*") if p.is_file()] == []
    assert (
        list(db_session.scalars(select(Document).where(Document.workspace_id == ws_uuid)))
        == []
    )
    assert (
        list(db_session.scalars(select(Invoice).where(Invoice.workspace_id == ws_uuid)))
        == []
    )


def test_document_scan_gating_safe_streaming_headers_rbac_csrf_and_isolation(
    make_client: Callable[..., TestClient],
    db_session: Session,
    storage_root: Path,
) -> None:
    admin_client = make_client()
    reviewer_client = make_client()
    uploader_client = make_client()
    viewer_client = make_client()
    foreign_client = make_client()
    uid = uuid.uuid4().hex[:8]

    reg_admin = _register_user(
        admin_client, prefix="doc_admin", org_name=f"Gate Firm {uid}"
    )
    org_id = reg_admin["organization"]["id"]
    ws1_id = reg_admin["workspace"]["workspaceId"]

    # Second workspace within the same organization for intra-org tenant isolation checks
    ws2_resp = admin_client.post(
        f"/api/v1/organizations/{org_id}/workspaces",
        headers=_csrf_headers(admin_client),
        json={
            "name": "Second Client",
            "workspaceCode": f"WS2-{uid}".upper(),
            "legalEntityName": "Second Client Pvt Ltd",
        },
    )
    assert ws2_resp.status_code == 201
    ws2_id = ws2_resp.json()["workspace"]["id"]

    reg_rev = _register_user(reviewer_client, prefix="doc_rev", full_name="Reviewer")
    reg_upl = _register_user(uploader_client, prefix="doc_upl", full_name="Uploader")
    reg_view = _register_user(viewer_client, prefix="doc_view", full_name="Viewer")
    _register_user(foreign_client, prefix="doc_for", org_name=f"Foreign Firm {uid}")

    _onboard_to_workspace(
        admin_client,
        org_id=org_id,
        workspace_id=ws1_id,
        member_client=reviewer_client,
        member_email=reg_rev["user"]["email"],
        workspace_role="REVIEWER",
    )
    _onboard_to_workspace(
        admin_client,
        org_id=org_id,
        workspace_id=ws1_id,
        member_client=uploader_client,
        member_email=reg_upl["user"]["email"],
        workspace_role="UPLOADER",
    )
    _onboard_to_workspace(
        admin_client,
        org_id=org_id,
        workspace_id=ws1_id,
        member_client=viewer_client,
        member_email=reg_view["user"]["email"],
        workspace_role="VIEWER",
    )

    sample_pdf = _pdf_bytes(70_000)

    # CSRF protection enforced on upload
    no_csrf = uploader_client.post(
        f"/api/v1/workspaces/{ws1_id}/documents",
        files={"file": ("nocsrf.pdf", sample_pdf, "application/pdf")},
    )
    assert no_csrf.status_code == 403
    assert no_csrf.json()["error"]["code"] == "CSRF_TOKEN_INVALID"

    bad_origin = uploader_client.post(
        f"/api/v1/workspaces/{ws1_id}/documents",
        headers=_csrf_headers(uploader_client, origin="https://evil.attacker.invalid"),
        files={"file": ("badorigin.pdf", sample_pdf, "application/pdf")},
    )
    assert bad_origin.status_code == 403
    assert bad_origin.json()["error"]["code"] == "CSRF_TOKEN_INVALID"

    # VIEWER denied upload (403 FORBIDDEN_ROLE)
    viewer_upload = viewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/documents",
        headers=_csrf_headers(viewer_client),
        files={"file": ("viewer.pdf", sample_pdf, "application/pdf")},
    )
    assert viewer_upload.status_code == 403
    assert viewer_upload.json()["error"]["code"] == "FORBIDDEN_ROLE"

    # UPLOADER, REVIEWER, WORKSPACE_ADMIN allowed upload
    upl_resp = uploader_client.post(
        f"/api/v1/workspaces/{ws1_id}/documents",
        headers=_csrf_headers(uploader_client),
        files={"file": ("invoice_scan.pdf", sample_pdf, "application/pdf")},
    )
    assert upl_resp.status_code == 201, upl_resp.text
    doc_id = upl_resp.json()["document"]["id"]
    doc_uuid = uuid.UUID(doc_id)

    rev_resp = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/documents",
        headers=_csrf_headers(reviewer_client),
        files={"file": ("reviewer.png", _png_bytes(512), "image/png")},
    )
    assert rev_resp.status_code == 201

    # 1. PENDING blocked (409 DOCUMENT_SCAN_NOT_CLEAN)
    pending_content = admin_client.get(
        f"/api/v1/workspaces/{ws1_id}/documents/{doc_id}/content"
    )
    assert pending_content.status_code == 409
    assert pending_content.json()["error"]["code"] == "DOCUMENT_SCAN_NOT_CLEAN"

    # 2. SKIPPED_DEV blocked (409 DOCUMENT_SCAN_NOT_CLEAN)
    db_doc = db_session.get(Document, doc_uuid)
    assert db_doc is not None
    db_doc.scan_status = "SKIPPED_DEV"
    db_session.commit()

    skipped_content = admin_client.get(
        f"/api/v1/workspaces/{ws1_id}/documents/{doc_id}/content"
    )
    assert skipped_content.status_code == 409
    assert skipped_content.json()["error"]["code"] == "DOCUMENT_SCAN_NOT_CLEAN"

    # 3. FAILED blocked (409 DOCUMENT_SCAN_NOT_CLEAN) — verifies PostgreSQL CHECK constraint too
    db_doc.scan_status = "FAILED"
    db_session.commit()

    failed_content = admin_client.get(
        f"/api/v1/workspaces/{ws1_id}/documents/{doc_id}/content"
    )
    assert failed_content.status_code == 409
    assert failed_content.json()["error"]["code"] == "DOCUMENT_SCAN_NOT_CLEAN"

    # 4. INFECTED blocked (403 DOCUMENT_INFECTED)
    db_doc.scan_status = "INFECTED"
    db_session.commit()

    infected_content = admin_client.get(
        f"/api/v1/workspaces/{ws1_id}/documents/{doc_id}/content"
    )
    assert infected_content.status_code == 403
    assert infected_content.json()["error"]["code"] == "DOCUMENT_INFECTED"

    # 5. CLEAN unlocks safe streaming with strict security headers to all active workspace roles
    db_doc.scan_status = "CLEAN"
    db_session.commit()

    for role_client in (admin_client, reviewer_client, uploader_client, viewer_client):
        inline_resp = role_client.get(
            f"/api/v1/workspaces/{ws1_id}/documents/{doc_id}/content"
        )
        assert inline_resp.status_code == 200
        assert inline_resp.content == sample_pdf
        assert inline_resp.headers["content-type"] == "application/pdf"
        assert inline_resp.headers["x-content-type-options"] == "nosniff"
        assert inline_resp.headers["cache-control"] == "private, no-store"
        assert inline_resp.headers["content-security-policy"] == "sandbox"
        assert (
            inline_resp.headers["content-disposition"]
            == 'inline; filename="invoice_scan.pdf"'
        )
        assert inline_resp.headers["content-length"] == str(len(sample_pdf))

    download_resp = viewer_client.get(
        f"/api/v1/workspaces/{ws1_id}/documents/{doc_id}/content",
        params={"download": "true"},
    )
    assert download_resp.status_code == 200
    assert (
        download_resp.headers["content-disposition"]
        == 'attachment; filename="invoice_scan.pdf"'
    )
    assert download_resp.headers["x-content-type-options"] == "nosniff"
    assert download_resp.headers["cache-control"] == "private, no-store"
    assert "content-security-policy" not in download_resp.headers

    # Inline PNG image preserves image headers without interfering with attachment behavior
    png_doc_id = rev_resp.json()["document"]["id"]
    png_db_doc = db_session.get(Document, uuid.UUID(png_doc_id))
    assert png_db_doc is not None
    png_db_doc.scan_status = "CLEAN"
    db_session.commit()
    png_inline = viewer_client.get(
        f"/api/v1/workspaces/{ws1_id}/documents/{png_doc_id}/content"
    )
    assert png_inline.status_code == 200
    assert png_inline.headers["content-type"] == "image/png"
    assert png_inline.headers["x-content-type-options"] == "nosniff"
    assert png_inline.headers["cache-control"] == "private, no-store"
    assert "content-security-policy" not in png_inline.headers

    # Cross-workspace isolation (foreign tenant + sibling workspace in same org) -> 404
    assert (
        admin_client.get(
            f"/api/v1/workspaces/{ws2_id}/documents/{doc_id}/content"
        ).status_code
        == 404
    )
    assert (
        foreign_client.get(
            f"/api/v1/workspaces/{ws1_id}/documents/{doc_id}/content"
        ).status_code
        == 404
    )
    assert (
        foreign_client.post(
            f"/api/v1/workspaces/{ws1_id}/documents",
            headers=_csrf_headers(foreign_client),
            files={"file": ("x.pdf", sample_pdf, "application/pdf")},
        ).status_code
        == 404
    )

    # Malformed UUID -> 422
    assert (
        admin_client.get(
            f"/api/v1/workspaces/{ws1_id}/documents/not-a-uuid/content"
        ).status_code
        == 422
    )

    # Missing file on disk for CLEAN DB row -> 404 without path leakage
    (storage_root / db_doc.storage_key).unlink()
    missing_disk = admin_client.get(
        f"/api/v1/workspaces/{ws1_id}/documents/{doc_id}/content"
    )
    assert missing_disk.status_code == 404
    assert missing_disk.json()["error"]["code"] == "DOCUMENT_CONTENT_NOT_FOUND"
    assert str(storage_root) not in missing_disk.text
