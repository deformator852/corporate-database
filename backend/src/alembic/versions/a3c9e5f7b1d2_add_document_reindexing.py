"""add document reindexing (processed again for a new embedding model)

Revision ID: a3c9e5f7b1d2
Revises: f2b6d8e3a4c5
Create Date: 2026-10-08 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3c9e5f7b1d2"
down_revision: str | Sequence[str] | None = "f2b6d8e3a4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("reindexing", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("documents", "reindexing")
