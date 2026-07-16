"""add trigram indexes for hybrid retrieval

Revision ID: 0003_hybrid_retrieval
Revises: 0002_email_verification
Create Date: 2026-07-13 19:50:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_hybrid_retrieval"
down_revision: str | Sequence[str] | None = "0002_email_verification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_content_trgm "
        "ON document_chunks USING gin (lower(content) gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notes_title_trgm "
        "ON notes USING gin (lower(title) gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notes_content_trgm "
        "ON notes USING gin (lower(content) gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_notes_content_trgm")
    op.execute("DROP INDEX IF EXISTS ix_notes_title_trgm")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_content_trgm")
