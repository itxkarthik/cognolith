"""share chat claims and the document queue across backend processes

- chat_generation_claims: one row per chat session with a reply being generated,
  renewed by its process's heartbeat; a stale row can be taken over. Cancel requests
  are a flag on the row, so they reach the process generating the reply.
- documents.processing_lease_until / processing_lease_token: the process running a
  document holds it until then; any process may claim a "processing" document
  without a live lease. The token keeps a holder that lost its lease from renewing
  or freeing the new one.
- ix_chat_messages_streaming: the interrupted-reply sweep, which runs every lease
  period in every process, reads only streaming replies.

Revision ID: 0016_multi_process_coordination
Revises: 0015_full_text_search_vectors
Create Date: 2026-11-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_multi_process_coordination"
down_revision: str | Sequence[str] | None = "0015_full_text_search_vectors"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_generation_claims",
        sa.Column("session_id", sa.Integer(), primary_key=True),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("owner", sa.String(length=128), nullable=False),
        sa.Column(
            "heartbeat_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_chat_generation_claims_message", "chat_generation_claims", ["message_id"])
    op.add_column(
        "documents",
        sa.Column("processing_lease_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "documents", sa.Column("processing_lease_token", sa.String(length=32), nullable=True)
    )
    op.create_index(
        "ix_chat_messages_streaming",
        "chat_messages",
        ["session_id"],
        postgresql_where=sa.text("generation_status = 'streaming'"),
    )


def downgrade() -> None:
    op.drop_index("ix_chat_messages_streaming", table_name="chat_messages")
    op.drop_column("documents", "processing_lease_token")
    op.drop_column("documents", "processing_lease_until")
    op.drop_index("ix_chat_generation_claims_message", table_name="chat_generation_claims")
    op.drop_table("chat_generation_claims")
