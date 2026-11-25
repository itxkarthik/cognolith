"""track refresh-token families for reuse detection

Revision ID: 0007_refresh_token_families
Revises: 0006_unique_google_drive_subject
Create Date: 2026-10-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0007_refresh_token_families"
down_revision: str | Sequence[str] | None = "0006_unique_google_drive_subject"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "refresh_tokens",
        sa.Column("family_id", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=True),
    )
    op.add_column("refresh_tokens", sa.Column("revoked_at", sa.DateTime(), nullable=True))
    # Existing tokens predate families; give each one its own.
    op.execute("UPDATE refresh_tokens SET family_id = md5(random()::text || id::text)")
    op.alter_column("refresh_tokens", "family_id", nullable=False)
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "revoked_at")
    op.drop_column("refresh_tokens", "family_id")
