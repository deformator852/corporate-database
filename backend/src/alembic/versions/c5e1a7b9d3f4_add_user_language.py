"""add users.language (the interface language the user chose)

Revision ID: c5e1a7b9d3f4
Revises: b4d0f6a8c2e3
Create Date: 2026-10-09 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c5e1a7b9d3f4"
down_revision: str | Sequence[str] | None = "b4d0f6a8c2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("language", sa.String(length=8), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "language")
