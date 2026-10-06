"""add document lines (digests of lines many documents share)

Revision ID: d9f4b6c0e2f9
Revises: c8e3a5b9d1e8
Create Date: 2026-10-05 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d9f4b6c0e2f9"
down_revision: str | Sequence[str] | None = "c8e3a5b9d1e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_lines",
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("digest", sa.LargeBinary(length=16), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("document_id", "digest"),
    )
    op.create_index("ix_document_lines_digest", "document_lines", ["digest"])


def downgrade() -> None:
    op.drop_index("ix_document_lines_digest", table_name="document_lines")
    op.drop_table("document_lines")
