"""add error_logs.category (unhandled, app or library)

Revision ID: f9b5d7e1a3c8
Revises: e8a4c6d0f2b7
Create Date: 2026-10-11 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f9b5d7e1a3c8"
down_revision: str | Sequence[str] | None = "e8a4c6d0f2b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from services.error_log import _OWN_MODULES, _UNHANDLED_LOGGERS

    op.add_column("error_logs", sa.Column("category", sa.String(length=16), server_default="library", nullable=False))
    op.create_index("ix_error_logs_category_created_at", "error_logs", ["category", "created_at"])
    # Entries from before: by their logger, as new ones are.
    unhandled = " OR ".join(f"logger LIKE '{name}%'" for name in _UNHANDLED_LOGGERS)
    op.execute(f"UPDATE error_logs SET category = 'unhandled' WHERE {unhandled}")
    own = ", ".join(f"'{name}'" for name in sorted(_OWN_MODULES))
    op.execute(
        f"UPDATE error_logs SET category = 'app' WHERE category = 'library' AND split_part(logger, '.', 1) IN ({own})"
    )


def downgrade() -> None:
    op.drop_index("ix_error_logs_category_created_at", table_name="error_logs")
    op.drop_column("error_logs", "category")
