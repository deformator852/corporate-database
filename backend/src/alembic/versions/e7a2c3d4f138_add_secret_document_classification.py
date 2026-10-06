"""add secret document classification

Revision ID: e7a2c3d4f138
Revises: d6f1b4c5e027
Create Date: 2026-09-22 12:42:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "e7a2c3d4f138"
down_revision: str | Sequence[str] | None = "d6f1b4c5e027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_documents_classification", "documents", type_="check")
    op.create_check_constraint(
        "ck_documents_classification",
        "documents",
        "classification IN ('standard','restricted','confidential','secret')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_documents_classification", "documents", type_="check")
    op.create_check_constraint(
        "ck_documents_classification",
        "documents",
        "classification IN ('standard','restricted','confidential')",
    )
