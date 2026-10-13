"""drop library warnings from the error log (they are no longer stored)

Revision ID: a1c3e5f7b9d2
Revises: f9b5d7e1a3c8
Create Date: 2026-10-13 18:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "a1c3e5f7b9d2"
down_revision: str | Sequence[str] | None = "f9b5d7e1a3c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DELETE FROM error_logs WHERE category = 'library' AND level = 'warning'")


def downgrade() -> None:
    pass  # deleted entries are gone
