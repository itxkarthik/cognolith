"""account security: case-insensitive emails, token version

- Emails are lower-cased and a unique index on lower(email) stops two accounts
  differing only in case. The upgrade refuses to run if such accounts exist.
- users.token_version is embedded in access tokens; bumping it revokes them all.

Revision ID: 0010_account_security
Revises: 0009_embedding_tables
Create Date: 2026-11-26 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_account_security"
down_revision: str | Sequence[str] | None = "0009_embedding_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX_NAME = "ix_users_email_lower"


def upgrade() -> None:
    duplicates = sa.text(
        "SELECT lower(email) FROM users GROUP BY lower(email) HAVING count(*) > 1 LIMIT 1"
    )
    duplicate = op.get_bind().execute(duplicates).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot make emails case-insensitive because several accounts share an "
            "address that differs only in letter case. Merge or remove the duplicate "
            "accounts, then rerun the migration."
        )
    op.execute("UPDATE users SET email = lower(email) WHERE email <> lower(email)")
    op.create_index(_INDEX_NAME, "users", [sa.text("lower(email)")], unique=True)
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
    op.drop_index(_INDEX_NAME, table_name="users")
