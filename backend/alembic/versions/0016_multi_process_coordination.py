"""share chat claims and the document queue across backend processes

- chat_generation_claims: one row per chat session with a reply being generated,
  renewed by its process's heartbeat; a stale row can be taken over. Cancel requests
  are a flag on the row, so they reach the process generating the reply.
- document_processing_leases: the process running a "processing" document holds a
  lease on it until lease_until; any process may claim a document without a live
  lease. The token keeps a holder that lost its lease from renewing or freeing the
  next one. Apart from the documents row, which a run keeps write-locked.
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
    op.create_table(
        "document_processing_leases",
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("token", sa.String(length=32), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_chat_messages_streaming",
        "chat_messages",
        ["session_id"],
        postgresql_where=sa.text("generation_status = 'streaming'"),
    )


def downgrade() -> None:
    op.drop_index("ix_chat_messages_streaming", table_name="chat_messages")
    op.drop_table("document_processing_leases")
    op.drop_index("ix_chat_generation_claims_message", table_name="chat_generation_claims")
    op.drop_table("chat_generation_claims")
