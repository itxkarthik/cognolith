"""record whether a document's chunks are embedded, and count processing runs

- documents.embedding_status: pending, indexed or failed. A document used to be
  "completed" even when embedding failed, so it looked searchable but wasn't.
- documents.processing_attempts: runs started, so a file that crashes the process
  is not resumed forever on every restart.

Existing completed documents are marked indexed when every chunk has a vector and
failed otherwise (the next search or chat embeds the missing chunks).

Revision ID: 0012_document_embedding_status
Revises: 0011_note_chunk_embeddings
Create Date: 2026-11-27 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_document_embedding_status"
down_revision: str | Sequence[str] | None = "0011_note_chunk_embeddings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "embedding_status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
    )
    op.add_column(
        "documents",
        sa.Column("processing_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.execute(
        """
        UPDATE documents d
        SET embedding_status = CASE
            WHEN EXISTS (
                SELECT 1
                FROM document_chunks dc
                LEFT JOIN chunk_embeddings ce ON ce.chunk_id = dc.id
                WHERE dc.document_id = d.id AND ce.chunk_id IS NULL
            ) THEN 'failed'
            ELSE 'indexed'
        END
        WHERE d.status = 'completed'
        """
    )


def downgrade() -> None:
    op.drop_column("documents", "processing_attempts")
    op.drop_column("documents", "embedding_status")
