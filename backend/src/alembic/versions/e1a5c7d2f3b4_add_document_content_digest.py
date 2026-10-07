"""add document content digest (refuse the same file twice)

Revision ID: e1a5c7d2f3b4
Revises: d9f4b6c0e2f9
Create Date: 2026-10-07 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e1a5c7d2f3b4"
down_revision: str | Sequence[str] | None = "d9f4b6c0e2f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("content_digest", sa.LargeBinary(length=16), nullable=True))
    op.create_index("ix_documents_content_digest", "documents", ["content_digest"])


def downgrade() -> None:
    op.drop_index("ix_documents_content_digest", table_name="documents")
    op.drop_column("documents", "content_digest")
