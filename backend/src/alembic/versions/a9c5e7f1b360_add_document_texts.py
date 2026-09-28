"""add document texts

Revision ID: a9c5e7f1b360
Revises: f8b4d5e6a249
Create Date: 2026-09-28 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a9c5e7f1b360"
down_revision: Union[str, Sequence[str], None] = "f8b4d5e6a249"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing documents are filled lazily: the first chat answer that needs
    # one parses the stored file once and saves the text.
    op.create_table(
        "document_texts",
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("document_id"),
    )


def downgrade() -> None:
    op.drop_table("document_texts")
