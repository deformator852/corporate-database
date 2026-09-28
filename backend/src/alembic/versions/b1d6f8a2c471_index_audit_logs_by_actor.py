"""index audit logs by actor

Revision ID: b1d6f8a2c471
Revises: a9c5e7f1b360
Create Date: 2026-09-28 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


revision: str = "b1d6f8a2c471"
down_revision: Union[str, Sequence[str], None] = "a9c5e7f1b360"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_audit_logs_actor_id_created_at",
        "audit_logs",
        ["actor_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_audit_logs_actor_email", "audit_logs", ["actor_email"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_actor_email", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_id_created_at", table_name="audit_logs")
