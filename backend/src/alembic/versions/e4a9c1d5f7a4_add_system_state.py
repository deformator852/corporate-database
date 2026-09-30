"""add system state

Revision ID: e4a9c1d5f7a4
Revises: d3f8b0c4e693
Create Date: 2026-09-30 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e4a9c1d5f7a4"
down_revision: Union[str, Sequence[str], None] = "d3f8b0c4e693"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_state",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )


def downgrade() -> None:
    op.drop_table("system_state")
