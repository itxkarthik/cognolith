"""add email verification codes

Revision ID: 0002_email_verification
Revises: 0001_baseline
Create Date: 2026-07-07 07:50:48.397134

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002_email_verification'
down_revision: Union[str, Sequence[str], None] = '0001_baseline'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Accounts present before this revision predate mandatory verification.
    op.execute("UPDATE users SET is_verified = TRUE")
    table_name = "email_verification_codes"
    inspector = sa.inspect(op.get_bind())
    expected_columns = {
        "user_id",
        "code_hash",
        "expires_at",
        "failed_attempts",
        "resend_available_at",
        "window_started_at",
        "send_count",
        "consumed_at",
        "created_at",
        "updated_at",
    }
    if table_name in inspector.get_table_names():
        actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
        if actual_columns != expected_columns:
            raise RuntimeError(
                "Existing email_verification_codes table does not match the expected schema"
            )
        return

    op.create_table(
        table_name,
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False),
        sa.Column("resend_available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("send_count", sa.Integer(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index(
        "ix_email_verification_expires_at", table_name, ["expires_at"], unique=False
    )
    op.create_index(
        "ix_email_verification_resend_available_at",
        table_name,
        ["resend_available_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_email_verification_resend_available_at', table_name='email_verification_codes')
    op.drop_index('ix_email_verification_expires_at', table_name='email_verification_codes')
    op.drop_table('email_verification_codes')
