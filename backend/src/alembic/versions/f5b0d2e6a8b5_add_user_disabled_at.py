"""add user disabled_at

Revision ID: f5b0d2e6a8b5
Revises: e4a9c1d5f7a4
Create Date: 2026-09-30 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f5b0d2e6a8b5"
down_revision: str | Sequence[str] | None = "e4a9c1d5f7a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "disabled_at")
