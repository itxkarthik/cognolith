"""add streaming chat generation lifecycle

Revision ID: 0004_streaming_chat
Revises: 0003_hybrid_retrieval
Create Date: 2026-07-18 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_streaming_chat"
down_revision: str | Sequence[str] | None = "0003_hybrid_retrieval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("generation_status", sa.String(20), nullable=True))
    op.add_column("chat_messages", sa.Column("generation_error", sa.Text(), nullable=True))
    op.add_column(
        "chat_messages", sa.Column("generation_metadata", postgresql.JSONB(), nullable=True)
    )
    op.add_column("chat_messages", sa.Column("generation_started_at", sa.DateTime(), nullable=True))
    op.add_column(
        "chat_messages", sa.Column("generation_completed_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "user_settings",
        sa.Column("rag_diagnostics_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        "UPDATE chat_messages SET generation_status = 'completed' WHERE role = 'assistant'"
    )


def downgrade() -> None:
    op.drop_column("user_settings", "rag_diagnostics_enabled")
    op.drop_column("chat_messages", "generation_completed_at")
    op.drop_column("chat_messages", "generation_started_at")
    op.drop_column("chat_messages", "generation_metadata")
    op.drop_column("chat_messages", "generation_error")
    op.drop_column("chat_messages", "generation_status")
