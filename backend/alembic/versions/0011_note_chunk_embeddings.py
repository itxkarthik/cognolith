"""embed notes per chunk instead of as one truncated vector

note_embeddings held one vector per note, built from its first 12,000 characters.
Notes are now split like documents, with one row per passage keyed by
(note_id, chunk_index), and the passage text is kept for citations.

The table is an index derived from the notes, so both directions empty it and the
next search or chat embeds every note again in the new shape.

Revision ID: 0011_note_chunk_embeddings
Revises: 0010_account_security
Create Date: 2026-11-27 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_note_chunk_embeddings"
down_revision: str | Sequence[str] | None = "0010_account_security"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "note_embeddings"
_PRIMARY_KEY = "note_embeddings_pkey"


def upgrade() -> None:
    op.execute(f"TRUNCATE {_TABLE}")
    op.add_column(_TABLE, sa.Column("chunk_index", sa.Integer(), nullable=False))
    op.add_column(_TABLE, sa.Column("content", sa.Text(), nullable=False))
    op.drop_constraint(_PRIMARY_KEY, _TABLE, type_="primary")
    op.create_primary_key(_PRIMARY_KEY, _TABLE, ["note_id", "chunk_index"])


def downgrade() -> None:
    op.execute(f"TRUNCATE {_TABLE}")
    op.drop_constraint(_PRIMARY_KEY, _TABLE, type_="primary")
    op.drop_column(_TABLE, "content")
    op.drop_column(_TABLE, "chunk_index")
    op.create_primary_key(_PRIMARY_KEY, _TABLE, ["note_id"])
