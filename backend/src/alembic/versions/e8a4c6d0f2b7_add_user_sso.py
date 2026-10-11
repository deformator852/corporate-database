"""add users.oidc_subject (SSO account) and allow users without a password

Revision ID: e8a4c6d0f2b7
Revises: d7f3b5c9e1a6
Create Date: 2026-10-11 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e8a4c6d0f2b7"
down_revision: str | Sequence[str] | None = "d7f3b5c9e1a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("oidc_subject", sa.String(length=512), nullable=True))
    op.create_unique_constraint("uq_users_oidc_subject", "users", ["oidc_subject"])
    op.alter_column("users", "password", existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM users WHERE password IS NULL")
    op.alter_column("users", "password", existing_type=sa.String(), nullable=False)
    op.drop_constraint("uq_users_oidc_subject", "users", type_="unique")
    op.drop_column("users", "oidc_subject")
