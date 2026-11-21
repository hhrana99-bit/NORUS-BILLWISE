"""Allow FAILED status in documents.scan_status check constraint.

Revision ID: 0003_doc_failed_scan_status
Revises: 0002_invites_and_rate_limits
Create Date: 2026-11-20 00:00:00+00:00

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_doc_failed_scan_status"
down_revision: str | Sequence[str] | None = "0002_invites_and_rate_limits"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_documents_document_scan_status_valid"),
        "documents",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_documents_document_scan_status_valid"),
        "documents",
        "scan_status IN ('PENDING', 'CLEAN', 'INFECTED', 'FAILED', 'SKIPPED_DEV')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_documents_document_scan_status_valid"),
        "documents",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_documents_document_scan_status_valid"),
        "documents",
        "scan_status IN ('PENDING', 'CLEAN', 'INFECTED', 'SKIPPED_DEV')",
    )
