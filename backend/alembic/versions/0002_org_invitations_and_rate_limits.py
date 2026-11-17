"""Add organization_invitations and auth_rate_limit_buckets tables.

Revision ID: 0002_invites_and_rate_limits
Revises: 0001_initial_foundation
Create Date: 2026-11-17 00:00:00+00:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_invites_and_rate_limits"
down_revision: str | Sequence[str] | None = "0001_initial_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organization_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invited_email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("invited_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('ORG_ADMIN', 'ORG_MEMBER')",
            name=op.f("ck_organization_invitations_org_invite_role_valid"),
        ),
        sa.CheckConstraint(
            "invited_email = lower(trim(invited_email))",
            name=op.f("ck_organization_invitations_org_invite_email_lower"),
        ),
        sa.ForeignKeyConstraint(
            ["accepted_by_user_id"],
            ["users.id"],
            name="fk_organization_invitations_accepted_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"],
            ["users.id"],
            name="fk_organization_invitations_invited_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_organization_invitations_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organization_invitations"),
        sa.UniqueConstraint("token_hash", name="uq_organization_invitations_token_hash"),
    )
    op.create_index(
        "ix_org_invitations_org_email",
        "organization_invitations",
        ["organization_id", "invited_email"],
        unique=False,
    )

    op.create_table(
        "auth_rate_limit_buckets",
        sa.Column("bucket_key", sa.String(length=255), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name=op.f("ck_auth_rate_limit_buckets_rate_limit_attempt_non_neg"),
        ),
        sa.PrimaryKeyConstraint("bucket_key", name="pk_auth_rate_limit_buckets"),
    )


def downgrade() -> None:
    op.drop_table("auth_rate_limit_buckets")
    op.drop_index("ix_org_invitations_org_email", table_name="organization_invitations")
    op.drop_table("organization_invitations")
