"""group ready notifications

Revision ID: b7d2f4a8c0d7
Revises: a6c1e3f7b9c6
Create Date: 2026-10-05 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7d2f4a8c0d7"
down_revision: Union[str, Sequence[str], None] = "a6c1e3f7b9c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TYPES = (
    "'document.completed',"
    "'document.store_failed',"
    "'document.queue_failed',"
    "'document.process_failed'"
)


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "ready_unannounced",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.drop_constraint("ck_notifications_type", "notifications", type_="check")
    op.create_check_constraint(
        "ck_notifications_type",
        "notifications",
        f"type IN ('documents.completed',{_TYPES})",
    )


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE type = 'documents.completed'")
    op.drop_constraint("ck_notifications_type", "notifications", type_="check")
    op.create_check_constraint("ck_notifications_type", "notifications", f"type IN ({_TYPES})")
    op.drop_column("documents", "ready_unannounced")
