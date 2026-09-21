"""allow document.completed notifications

Revision ID: c5e0a2b3d916
Revises: b4d9f3a1c805
Create Date: 2026-09-21 12:38:00.000000

"""

from typing import Sequence, Union

from alembic import op


revision: str = "c5e0a2b3d916"
down_revision: Union[str, Sequence[str], None] = "b4d9f3a1c805"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("notifications_type_check", "notifications", type_="check")
    op.create_check_constraint(
        "ck_notifications_type",
        "notifications",
        "type IN ("
        "'document.completed',"
        "'document.store_failed',"
        "'document.queue_failed',"
        "'document.process_failed'"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint("ck_notifications_type", "notifications", type_="check")
    op.create_check_constraint(
        "notifications_type_check",
        "notifications",
        "type IN ("
        "'document.store_failed',"
        "'document.queue_failed',"
        "'document.process_failed'"
        ")",
    )
