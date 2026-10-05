"""drop document cleaning status (the LLM cleanup step is gone)

Revision ID: c8e3a5b9d1e8
Revises: b7d2f4a8c0d7
Create Date: 2026-10-05 15:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


revision: str = "c8e3a5b9d1e8"
down_revision: Union[str, Sequence[str], None] = "b7d2f4a8c0d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Interrupted mid-cleanup: the worker processes queued documents again.
    op.execute("UPDATE documents SET status = 'queued' WHERE status = 'cleaning'")
    op.drop_constraint("documents_status_check", "documents", type_="check")
    op.create_check_constraint(
        "documents_status_check",
        "documents",
        "status IN ('queued','parsing','chunking','embedding','completed','failed')",
    )


def downgrade() -> None:
    op.drop_constraint("documents_status_check", "documents", type_="check")
    op.create_check_constraint(
        "documents_status_check",
        "documents",
        "status IN ('queued','parsing','chunking','cleaning','embedding',"
        "'completed','failed')",
    )
