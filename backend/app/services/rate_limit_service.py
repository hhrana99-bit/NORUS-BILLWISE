from __future__ import annotations

import hashlib
import math
from datetime import datetime, timedelta, timezone

from fastapi import Request, status
from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.errors import AppError
from app.models.tenancy import AuthRateLimitBucket, utc_now


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _hash_identifier(raw: str) -> str:
    return hashlib.sha256(raw.strip().lower().encode("utf-8")).hexdigest()[:32]


def check_and_increment_bucket(
    db: Session,
    *,
    bucket_key: str,
    max_attempts: int,
    window_seconds: int,
    now: datetime | None = None,
) -> None:
    """Atomically increment a PostgreSQL rate-limit bucket shared across all app workers."""
    current_time = now or utc_now()
    window_delta = timedelta(seconds=window_seconds)
    window_cutoff = current_time - window_delta

    table = AuthRateLimitBucket.__table__
    is_blocked = (table.c.blocked_until.is_not(None)) & (
        table.c.blocked_until > current_time
    )
    window_expired = table.c.window_started_at <= window_cutoff

    next_window_start = case(
        (is_blocked, table.c.window_started_at),
        (window_expired, current_time),
        else_=table.c.window_started_at,
    )
    next_attempt_count = case(
        (is_blocked, table.c.attempt_count),
        (window_expired, 1),
        else_=table.c.attempt_count + 1,
    )
    next_blocked_until = case(
        (is_blocked, table.c.blocked_until),
        (window_expired, None),
        (
            (table.c.attempt_count + 1) > max_attempts,
            table.c.window_started_at + window_delta,
        ),
        else_=None,
    )

    stmt = (
        pg_insert(AuthRateLimitBucket)
        .values(
            bucket_key=bucket_key,
            window_started_at=current_time,
            attempt_count=1,
            blocked_until=None,
            updated_at=current_time,
        )
        .on_conflict_do_update(
            index_elements=[AuthRateLimitBucket.bucket_key],
            set_={
                "window_started_at": next_window_start,
                "attempt_count": next_attempt_count,
                "blocked_until": next_blocked_until,
                "updated_at": current_time,
            },
        )
        .returning(
            AuthRateLimitBucket.attempt_count,
            AuthRateLimitBucket.blocked_until,
        )
    )

    row = db.execute(stmt).first()
    db.commit()

    if row is None:
        return

    attempt_count, blocked_until = int(row[0]), row[1]
    if blocked_until is not None:
        blocked_utc = _ensure_utc(blocked_until)
        if blocked_utc > current_time:
            retry_after = max(
                1, int(math.ceil((blocked_utc - current_time).total_seconds()))
            )
            raise AppError(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                code="RATE_LIMITED",
                message="Too many authentication attempts. Please retry shortly.",
                details={"retryAfterSeconds": retry_after},
                headers={"Retry-After": str(retry_after)},
            )
    elif attempt_count > max_attempts:
        retry_after = max(1, int(window_seconds))
        raise AppError(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="RATE_LIMITED",
            message="Too many authentication attempts. Please retry shortly.",
            details={"retryAfterSeconds": retry_after},
            headers={"Retry-After": str(retry_after)},
        )


def enforce_auth_rate_limit(
    request: Request,
    settings: Settings,
    *,
    action: str,
    ip_address: str | None,
    account_identifier: str | None = None,
) -> None:
    """Enforce multi-worker PostgreSQL rate limiting using an isolated committed session."""
    if not settings.rate_limit_enabled:
        return

    limit_map = {
        "login": settings.login_rate_limit_max_attempts,
        "register": settings.register_rate_limit_max_attempts,
        "refresh": settings.refresh_rate_limit_max_attempts,
    }
    max_attempts = limit_map[action]
    window_seconds = settings.rate_limit_window_seconds

    ip_part = _hash_identifier(ip_address or "unknown")
    session_factory: sessionmaker[Session] = request.app.state.session_factory

    with session_factory() as rl_db:
        check_and_increment_bucket(
            rl_db,
            bucket_key=f"{action}:ip:{ip_part}",
            max_attempts=max_attempts,
            window_seconds=window_seconds,
        )
        if account_identifier:
            acct_part = _hash_identifier(account_identifier)
            check_and_increment_bucket(
                rl_db,
                bucket_key=f"{action}:acct:{acct_part}",
                max_attempts=max_attempts,
                window_seconds=window_seconds,
            )
