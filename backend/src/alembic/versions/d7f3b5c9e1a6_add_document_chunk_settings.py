"""add documents.chunk_size and chunk_overlap (the settings its chunks were cut with)

Revision ID: d7f3b5c9e1a6
Revises: c5e1a7b9d3f4
Create Date: 2026-10-09 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d7f3b5c9e1a6"
down_revision: str | Sequence[str] | None = "c5e1a7b9d3f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from settings import chunk_overlap, chunk_size

    op.add_column("documents", sa.Column("chunk_size", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("chunk_overlap", sa.Integer(), nullable=True))
    # Not recorded before: assume the settings in effect at the upgrade.
    op.execute(
        sa.text(
            "UPDATE documents SET chunk_size = :size, chunk_overlap = :overlap WHERE status = 'completed'"
        ).bindparams(size=chunk_size(), overlap=chunk_overlap())
    )


def downgrade() -> None:
    op.drop_column("documents", "chunk_overlap")
    op.drop_column("documents", "chunk_size")
