"""add chat message ratings

Revision ID: f2b6d8e3a4c5
Revises: e1a5c7d2f3b4
Create Date: 2026-10-07 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f2b6d8e3a4c5"
down_revision: str | Sequence[str] | None = "e1a5c7d2f3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("rating", sa.SmallInteger(), nullable=True))
    op.add_column("chat_messages", sa.Column("rated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint("ck_chat_messages_rating", "chat_messages", "rating IN (-1, 1)")
    op.create_index("ix_chat_messages_rated_at", "chat_messages", ["rated_at"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_rated_at", table_name="chat_messages")
    op.drop_constraint("ck_chat_messages_rating", "chat_messages", type_="check")
    op.drop_column("chat_messages", "rated_at")
    op.drop_column("chat_messages", "rating")
