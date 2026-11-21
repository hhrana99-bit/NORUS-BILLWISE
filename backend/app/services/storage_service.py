from __future__ import annotations

import hashlib
import os
import posixpath
import re
import tempfile
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

from fastapi import status

from app.core.errors import AppError

MAX_DOCUMENT_BYTES = 15 * 1024 * 1024  # 15 MB (15,728,640 bytes)
MAX_MULTIPART_OVERHEAD_BYTES = 1 * 1024 * 1024  # 1 MiB (1,048,576 bytes) for multipart boundaries/fields
MAX_DOCUMENT_UPLOAD_REQUEST_BYTES = (
    MAX_DOCUMENT_BYTES + MAX_MULTIPART_OVERHEAD_BYTES
)  # 16 MiB (16,777,216 bytes) total HTTP request-body cap enforced before multipart parsing
STREAM_CHUNK_SIZE = 65_536  # 64 KB bounded streaming chunks
MAGIC_HEADER_PEEK_BYTES = 16

_SAFE_FILENAME_CHARS_RE = re.compile(r"[^A-Za-z0-9._ -]+")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True)
class DocumentFormatSpec:
    format_name: str
    canonical_ext: str
    canonical_mime: str
    allowed_extensions: frozenset[str]
    allowed_mimes: frozenset[str]


_FORMAT_PDF = DocumentFormatSpec(
    format_name="PDF",
    canonical_ext=".pdf",
    canonical_mime="application/pdf",
    allowed_extensions=frozenset({".pdf"}),
    allowed_mimes=frozenset({"application/pdf"}),
)
_FORMAT_PNG = DocumentFormatSpec(
    format_name="PNG",
    canonical_ext=".png",
    canonical_mime="image/png",
    allowed_extensions=frozenset({".png"}),
    allowed_mimes=frozenset({"image/png"}),
)
_FORMAT_JPEG = DocumentFormatSpec(
    format_name="JPEG",
    canonical_ext=".jpg",
    canonical_mime="image/jpeg",
    allowed_extensions=frozenset({".jpg", ".jpeg"}),
    allowed_mimes=frozenset({"image/jpeg", "image/jpg"}),
)
_FORMAT_WEBP = DocumentFormatSpec(
    format_name="WEBP",
    canonical_ext=".webp",
    canonical_mime="image/webp",
    allowed_extensions=frozenset({".webp"}),
    allowed_mimes=frozenset({"image/webp"}),
)

_SUPPORTED_FORMATS: tuple[DocumentFormatSpec, ...] = (
    _FORMAT_PDF,
    _FORMAT_PNG,
    _FORMAT_JPEG,
    _FORMAT_WEBP,
)

_EXT_TO_FORMAT: dict[str, DocumentFormatSpec] = {
    ext: spec for spec in _SUPPORTED_FORMATS for ext in spec.allowed_extensions
}


@dataclass(frozen=True)
class StoredDocumentObject:
    storage_key: str
    byte_size: int
    sha256_checksum: str


class DocumentStorage(Protocol):
    """Pluggable storage interface for invoice documents (local filesystem or object store)."""

    def save_stream(
        self,
        *,
        storage_key: str,
        stream: BinaryIO,
        max_bytes: int = MAX_DOCUMENT_BYTES,
        chunk_size: int = STREAM_CHUNK_SIZE,
        header_validator: Callable[[bytes], None] | None = None,
    ) -> StoredDocumentObject:
        ...

    def open_stream(
        self,
        storage_key: str,
        *,
        chunk_size: int = STREAM_CHUNK_SIZE,
    ) -> Iterator[bytes]:
        ...

    def delete(self, storage_key: str) -> None:
        ...


def sanitize_original_filename(
    raw_filename: str | None, *, fallback_ext: str = ""
) -> str:
    """Extract a safe, single-component ASCII filename metadata string (<= 255 chars)."""
    candidate = (raw_filename or "").replace("\x00", "")
    # Strip both POSIX and Windows path prefixes without trusting client paths
    candidate = candidate.replace("\\", "/").split("/")[-1]
    candidate = _CONTROL_CHARS_RE.sub("", candidate).strip()
    candidate = _SAFE_FILENAME_CHARS_RE.sub("_", candidate)
    candidate = " ".join(candidate.split()).lstrip(".")
    candidate = candidate.strip(" ._")

    if not candidate:
        return f"document{fallback_ext}"

    if len(candidate) > 255:
        stem, dot, ext = candidate.rpartition(".")
        if dot and ext and len(ext) <= 16:
            max_stem_len = max(1, 255 - 1 - len(ext))
            candidate = f"{stem[:max_stem_len]}.{ext}"
        else:
            candidate = candidate[:255]
    return candidate


def _extract_raw_extension(raw_filename: str | None) -> str:
    if not raw_filename:
        return ""
    cleaned = raw_filename.replace("\x00", "").replace("\\", "/").split("/")[-1].strip()
    _, ext = posixpath.splitext(cleaned)
    return ext.lower()


def validate_declared_upload_type(
    *,
    raw_filename: str | None,
    declared_content_type: str | None,
) -> tuple[DocumentFormatSpec, str]:
    """Validate extension and declared MIME consistency before streaming to storage."""
    ext = _extract_raw_extension(raw_filename)
    expected_spec = _EXT_TO_FORMAT.get(ext)
    if expected_spec is None:
        raise AppError(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            code="UNSUPPORTED_MEDIA_TYPE",
            message="Only PDF, PNG, JPEG, and WEBP invoice documents are supported.",
        )

    normalized_mime = (
        (declared_content_type or "").split(";")[0].strip().lower()
    )
    if normalized_mime not in expected_spec.allowed_mimes:
        raise AppError(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            code="UNSUPPORTED_MEDIA_TYPE",
            message="Declared file Content-Type does not match an allowed PDF, PNG, JPEG, or WEBP document.",
        )

    safe_filename = sanitize_original_filename(
        raw_filename, fallback_ext=expected_spec.canonical_ext
    )
    return expected_spec, safe_filename


def detect_magic_format(header_bytes: bytes) -> DocumentFormatSpec | None:
    """Identify supported document type strictly from binary magic-byte signatures."""
    if header_bytes.startswith(b"%PDF-"):
        return _FORMAT_PDF
    if header_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return _FORMAT_PNG
    if header_bytes.startswith(b"\xff\xd8\xff"):
        return _FORMAT_JPEG
    if (
        len(header_bytes) >= 12
        and header_bytes[:4] == b"RIFF"
        and header_bytes[8:12] == b"WEBP"
    ):
        return _FORMAT_WEBP
    return None


def verify_magic_bytes_match_format(
    header_bytes: bytes, expected_spec: DocumentFormatSpec
) -> None:
    """Verify binary magic signature matches the declared extension and MIME type."""
    detected = detect_magic_format(header_bytes)
    if detected is None or detected.format_name != expected_spec.format_name:
        raise AppError(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            code="UNSUPPORTED_MEDIA_TYPE",
            message="File signature does not match the declared PDF, PNG, JPEG, or WEBP format.",
        )


def build_workspace_document_storage_key(
    *,
    organization_id: uuid.UUID,
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    canonical_ext: str,
) -> str:
    """Generate a server-controlled UUID storage key free of any client-supplied path data."""
    if canonical_ext not in _EXT_TO_FORMAT:
        raise ValueError("Unsupported canonical document extension.")
    return f"orgs/{organization_id}/workspaces/{workspace_id}/{document_id}{canonical_ext}"


class LocalFilesystemStorage:
    """Local filesystem DocumentStorage adapter with strict canonical root containment."""

    def __init__(self, root_dir: str | Path) -> None:
        raw_root = str(root_dir).strip()
        if not raw_root:
            raise ValueError("Document storage root cannot be blank.")
        self._root = Path(raw_root).resolve()

    @property
    def root(self) -> Path:
        return self._root

    def _resolve_safe_path(self, storage_key: str) -> Path:
        if not storage_key or "\x00" in storage_key:
            raise AppError(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="STORAGE_PATH_INVALID",
                message="Invalid document storage key.",
            )
        if "\\" in storage_key or storage_key.startswith("/") or _WINDOWS_DRIVE_RE.match(storage_key):
            raise AppError(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="STORAGE_PATH_INVALID",
                message="Invalid document storage key.",
            )

        segments = storage_key.split("/")
        if any(seg in {"", ".", ".."} for seg in segments):
            raise AppError(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="STORAGE_PATH_INVALID",
                message="Invalid document storage key.",
            )

        candidate = (self._root / storage_key).resolve()
        if candidate == self._root or not candidate.is_relative_to(self._root):
            raise AppError(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="STORAGE_PATH_INVALID",
                message="Invalid document storage key.",
            )
        return candidate

    def save_stream(
        self,
        *,
        storage_key: str,
        stream: BinaryIO,
        max_bytes: int = MAX_DOCUMENT_BYTES,
        chunk_size: int = STREAM_CHUNK_SIZE,
        header_validator: Callable[[bytes], None] | None = None,
    ) -> StoredDocumentObject:
        if chunk_size < 1 or chunk_size > STREAM_CHUNK_SIZE:
            raise ValueError(
                f"chunk_size must be between 1 and {STREAM_CHUNK_SIZE} bytes."
            )
        if max_bytes < 1 or max_bytes > MAX_DOCUMENT_BYTES:
            raise ValueError(
                f"max_bytes must be between 1 and {MAX_DOCUMENT_BYTES} bytes."
            )

        target_path = self._resolve_safe_path(storage_key)

        # Peek up to MAGIC_HEADER_PEEK_BYTES via <= chunk_size reads before creating disk state.
        # Note: if a caller supplies tiny chunks (< 16 bytes), gather up to MAGIC_HEADER_PEEK_BYTES
        # without ever buffering more than chunk_size + MAGIC_HEADER_PEEK_BYTES in RAM.
        first_chunk = stream.read(chunk_size)
        if not first_chunk:
            raise AppError(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="EMPTY_FILE",
                message="Uploaded document file cannot be empty.",
            )

        initial_chunks: list[bytes] = [first_chunk]
        total_bytes = len(first_chunk)
        if total_bytes > max_bytes:
            raise AppError(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                code="FILE_TOO_LARGE",
                message="Uploaded document exceeds the 15 MB maximum file size.",
            )

        while total_bytes < MAGIC_HEADER_PEEK_BYTES:
            more = stream.read(chunk_size)
            if not more:
                break
            total_bytes += len(more)
            if total_bytes > max_bytes:
                raise AppError(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    code="FILE_TOO_LARGE",
                    message="Uploaded document exceeds the 15 MB maximum file size.",
                )
            initial_chunks.append(more)

        header_sample = b"".join(initial_chunks)[:MAGIC_HEADER_PEEK_BYTES]
        if header_validator is not None:
            header_validator(header_sample)

        target_path.parent.mkdir(parents=True, exist_ok=True)
        # Re-verify directory containment after creation in case of pre-existing symlink
        if not target_path.parent.resolve().is_relative_to(self._root):
            raise AppError(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="STORAGE_PATH_INVALID",
                message="Invalid document storage key.",
            )

        sha256 = hashlib.sha256()
        tmp_path: Path | None = None
        try:
            fd, raw_tmp = tempfile.mkstemp(
                prefix=".upload_",
                suffix=".part",
                dir=str(target_path.parent),
            )
            tmp_path = Path(raw_tmp)
            with os.fdopen(fd, "wb") as out_fp:
                for initial_part in initial_chunks:
                    sha256.update(initial_part)
                    out_fp.write(initial_part)
                initial_chunks.clear()

                while True:
                    chunk = stream.read(chunk_size)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        raise AppError(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            code="FILE_TOO_LARGE",
                            message="Uploaded document exceeds the 15 MB maximum file size.",
                        )
                    sha256.update(chunk)
                    out_fp.write(chunk)

                out_fp.flush()
                os.fsync(out_fp.fileno())

            os.replace(tmp_path, target_path)
            tmp_path = None
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass

        return StoredDocumentObject(
            storage_key=storage_key,
            byte_size=total_bytes,
            sha256_checksum=sha256.hexdigest(),
        )

    def open_stream(
        self,
        storage_key: str,
        *,
        chunk_size: int = STREAM_CHUNK_SIZE,
    ) -> Iterator[bytes]:
        if chunk_size < 1 or chunk_size > STREAM_CHUNK_SIZE:
            raise ValueError(
                f"chunk_size must be between 1 and {STREAM_CHUNK_SIZE} bytes."
            )

        target_path = self._resolve_safe_path(storage_key)
        if not target_path.is_file():
            raise AppError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="DOCUMENT_CONTENT_NOT_FOUND",
                message="Document content is not available.",
            )

        def _chunk_generator() -> Iterator[bytes]:
            with target_path.open("rb") as in_fp:
                while True:
                    chunk = in_fp.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk

        return _chunk_generator()

    def delete(self, storage_key: str) -> None:
        target_path = self._resolve_safe_path(storage_key)
        try:
            target_path.unlink(missing_ok=True)
        except OSError:
            pass
