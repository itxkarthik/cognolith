"""create the pgvector embedding tables in migrations

The tables used to be created on the first chat or search request, with the vector
size taken from whichever embedding model ran first. They are now created here at
EMBEDDING_DIMENSIONS. Installs that already have them keep their tables; startup
validation reports a size that differs from the configuration.

Revision ID: 0009_embedding_tables
Revises: 0008_hnsw_embedding_indexes
Create Date: 2026-10-24 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

from app.core.config import settings

revision: str = "0009_embedding_tables"
down_revision: str | Sequence[str] | None = "0008_hnsw_embedding_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    dimensions = int(settings.EMBEDDING_DIMENSIONS)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS chunk_embeddings (
            chunk_id INTEGER PRIMARY KEY REFERENCES document_chunks(id) ON DELETE CASCADE,
            document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            model VARCHAR(100) NOT NULL,
            embedding vector({dimensions}) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS note_embeddings (
            note_id INTEGER PRIMARY KEY REFERENCES notes(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            model VARCHAR(100) NOT NULL,
            content_hash VARCHAR(64) NOT NULL,
            embedding vector({dimensions}) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS chat_message_embeddings (
            message_id INTEGER PRIMARY KEY REFERENCES chat_messages(id) ON DELETE CASCADE,
            session_id INTEGER NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            model VARCHAR(100) NOT NULL,
            content_hash VARCHAR(64) NOT NULL,
            embedding vector({dimensions}) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chunk_embeddings_user_document "
        "ON chunk_embeddings (user_id, document_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_note_embeddings_user ON note_embeddings (user_id, note_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chat_message_embeddings_user_session "
        "ON chat_message_embeddings (user_id, session_id)"
    )
    for table in ("chunk_embeddings", "note_embeddings", "chat_message_embeddings"):
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_embedding_hnsw "
            f"ON {table} USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    # Embeddings are derived data; they are rebuilt on demand after re-upgrading
    for table in ("chat_message_embeddings", "note_embeddings", "chunk_embeddings"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
