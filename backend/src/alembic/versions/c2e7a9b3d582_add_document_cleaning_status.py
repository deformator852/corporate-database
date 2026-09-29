"""add document cleaning status

Revision ID: c2e7a9b3d582
Revises: b1d6f8a2c471
Create Date: 2026-09-29 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


revision: str = "c2e7a9b3d582"
down_revision: Union[str, Sequence[str], None] = "b1d6f8a2c471"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("documents_status_check", "documents", type_="check")
    op.create_check_constraint(
        "documents_status_check",
        "documents",
        "status IN ('queued','parsing','chunking','cleaning','embedding',"
        "'completed','failed')",
    )


def downgrade() -> None:
    op.execute("UPDATE documents SET status = 'embedding' WHERE status = 'cleaning'")
    op.drop_constraint("documents_status_check", "documents", type_="check")
    op.create_check_constraint(
        "documents_status_check",
        "documents",
        "status IN ('queued','parsing','chunking','embedding','completed','failed')",
    )
