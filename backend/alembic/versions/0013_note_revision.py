"""add a per-write revision to notes for conflict detection

notes.version only grows when a history snapshot is taken (at most every few
minutes), so it can't tell whether a note changed since an editor loaded it.
notes.revision is bumped on every write; an update that names a stale revision
is refused with 409 instead of overwriting newer content.

Revision ID: 0013_note_revision
Revises: 0012_document_embedding_status
Create Date: 2026-11-27 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_note_revision"
down_revision: str | Sequence[str] | None = "0012_document_embedding_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notes",
        sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )


def downgrade() -> None:
    op.drop_column("notes", "revision")
