"""add document classification

Revision ID: d6f1b4c5e027
Revises: c5e0a2b3d916
Create Date: 2026-09-22 12:32:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d6f1b4c5e027"
down_revision: str | Sequence[str] | None = "c5e0a2b3d916"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "classification",
            sa.String(length=20),
            nullable=False,
            server_default="standard",
        ),
    )
    op.create_check_constraint(
        "ck_documents_classification",
        "documents",
        "classification IN ('standard','restricted','confidential')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_documents_classification", "documents", type_="check")
    op.drop_column("documents", "classification")
