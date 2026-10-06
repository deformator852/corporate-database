"""add chat requests

Revision ID: a6c1e3f7b9c6
Revises: f5b0d2e6a8b5
Create Date: 2026-09-30 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a6c1e3f7b9c6"
down_revision: str | Sequence[str] | None = "f5b0d2e6a8b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_requests",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_requests_user_id_started_at", "chat_requests", ["user_id", "started_at"])
    op.create_index(
        "uq_chat_requests_one_open_per_user",
        "chat_requests",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("finished_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("chat_requests")
