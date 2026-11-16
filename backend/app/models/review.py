from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.tenancy import Organization, User, Workspace, utc_now

if TYPE_CHECKING:
    from app.models.accounting import Invoice


class InvoiceReviewFlag(Base):
    __tablename__ = "invoice_review_flags"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "invoice_id"],
            ["invoices.workspace_id", "invoices.id"],
            ondelete="RESTRICT",
            name="fk_review_flags_workspace_invoice",
        ),
        CheckConstraint(
            "char_length(trim(reason_text)) > 0",
            name="flag_reason_not_empty",
        ),
        CheckConstraint(
            "status IN ('OPEN', 'RESOLVED', 'DISMISSED')",
            name="flag_status_valid",
        ),
        Index(
            "ix_invoice_review_flags_lookup",
            "workspace_id",
            "invoice_id",
            "status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    flag_category: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=text("'OPEN'"), default="OPEN"
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=utc_now,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    invoice: Mapped[Invoice] = relationship(
        back_populates="review_flags",
        foreign_keys=[workspace_id, invoice_id],
    )
    created_by_user: Mapped[User] = relationship(foreign_keys=[created_by_user_id])
    resolved_by_user: Mapped[User | None] = relationship(
        foreign_keys=[resolved_by_user_id]
    )


class ReviewAction(Base):
    __tablename__ = "review_actions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "invoice_id"],
            ["invoices.workspace_id", "invoices.id"],
            ondelete="RESTRICT",
            name="fk_review_actions_workspace_invoice",
        ),
        Index(
            "ix_review_actions_lookup",
            "workspace_id",
            "invoice_id",
            text("created_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_status: Mapped[str] = mapped_column(String(24), nullable=False)
    new_status: Mapped[str] = mapped_column(String(24), nullable=False)
    variance_acknowledged: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    variance_amount_at_action: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_changes: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=utc_now,
    )

    invoice: Mapped[Invoice] = relationship(
        back_populates="review_actions",
        foreign_keys=[workspace_id, invoice_id],
    )
    actor_user: Mapped[User] = relationship()


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "tone IN ('neutral', 'success', 'warning')",
            name="audit_event_tone_valid",
        ),
        Index("ix_audit_events_workspace_created", "workspace_id", text("created_at DESC")),
        Index("ix_audit_events_org_created", "organization_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=True,
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(48), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    tone: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'neutral'"), default="neutral"
    )
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=utc_now,
    )

    organization: Mapped[Organization] = relationship(back_populates="audit_events")
    workspace: Mapped[Workspace | None] = relationship(back_populates="audit_events")
    actor_user: Mapped[User | None] = relationship()
