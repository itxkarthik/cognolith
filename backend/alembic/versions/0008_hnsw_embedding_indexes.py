"""replace ivfflat embedding indexes with HNSW

ivfflat trains its centroids when the index is built, and these indexes were built
on near-empty tables the first time a query ran, so recall was poor. HNSW needs no
training. The embedding tables are created lazily by PgVectorStore.ensure_schema,
so this only converts tables that already exist.

Revision ID: 0008_hnsw_embedding_indexes
Revises: 0007_refresh_token_families
Create Date: 2026-10-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_hnsw_embedding_indexes"
down_revision: str | Sequence[str] | None = "0007_refresh_token_families"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("chunk_embeddings", "note_embeddings", "chat_message_embeddings")


def _table_exists(table: str) -> bool:
    return bool(
        op.get_bind().execute(sa.text("SELECT to_regclass(:table) IS NOT NULL"), {"table": table}).scalar()
    )


def upgrade() -> None:
    for table in _TABLES:
        if not _table_exists(table):
            continue
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_embedding_cosine")
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_embedding_hnsw "
            f"ON {table} USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    for table in _TABLES:
        if not _table_exists(table):
            continue
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_embedding_hnsw")
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_embedding_cosine "
            f"ON {table} USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
        )
