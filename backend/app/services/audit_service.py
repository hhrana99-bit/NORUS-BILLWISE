from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.review import AuditEvent
from app.models.tenancy import User


def record_audit_event(
    db: Session,
    *,
    organization_id: uuid.UUID,
    workspace_id: uuid.UUID | None = None,
    actor_user: User | None = None,
    actor_display_name: str | None = None,
    event_type: str,
    entity_type: str,
    entity_id: uuid.UUID | None = None,
    summary: str,
    tone: str = "neutral",
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditEvent:
    """Append an immutable compliance/security event to audit_events."""
    resolved_actor_name = (
        actor_display_name
        or (actor_user.full_name if actor_user is not None else None)
        or "System"
    )
    event = AuditEvent(
        organization_id=organization_id,
        workspace_id=workspace_id,
        actor_user_id=actor_user.id if actor_user is not None else None,
        actor_display_name=resolved_actor_name,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        tone=tone,
        event_metadata=metadata or {},
        ip_address=(ip_address or "")[:64] or None,
    )
    db.add(event)
    return event


def list_workspace_audit_events(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    restrict_to_actor_user_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    event_type: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[AuditEvent], int]:
    """Return paginated audit events strictly scoped to a single workspace."""
    if date_from is not None and date_to is not None and date_from > date_to:
        raise AppError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="VALIDATION_ERROR",
            message="dateFrom cannot be after dateTo.",
        )

    conditions = [AuditEvent.workspace_id == workspace_id]

    if restrict_to_actor_user_id is not None:
        conditions.append(AuditEvent.actor_user_id == restrict_to_actor_user_id)
    elif actor_user_id is not None:
        conditions.append(AuditEvent.actor_user_id == actor_user_id)

    if entity_type:
        conditions.append(AuditEvent.entity_type == entity_type)
    if entity_id is not None:
        conditions.append(AuditEvent.entity_id == entity_id)
    if event_type:
        conditions.append(AuditEvent.event_type == event_type)
    if date_from is not None:
        conditions.append(AuditEvent.created_at >= date_from)
    if date_to is not None:
        conditions.append(AuditEvent.created_at <= date_to)

    total = db.scalar(select(func.count(AuditEvent.id)).where(*conditions)) or 0
    rows = list(
        db.scalars(
            select(AuditEvent)
            .where(*conditions)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return rows, int(total)
