"""let a client repeat a note create safely

notes.client_request_id holds an optional key the client sends with a create it may
repeat, such as an offline write replayed after its response was lost, or replayed by
two tabs. A unique (user_id, client_request_id) index makes the repeat return the
note the first send created instead of a duplicate. NULLs don't collide, so creates
without a key are unaffected.

Revision ID: 0014_note_client_request_id
Revises: 0013_note_revision
Create Date: 2026-11-27 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_note_client_request_id"
down_revision: str | Sequence[str] | None = "0013_note_revision"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "uix_notes_user_client_request_id"


def upgrade() -> None:
    op.add_column("notes", sa.Column("client_request_id", sa.String(length=64), nullable=True))
    op.create_index(_INDEX, "notes", ["user_id", "client_request_id"], unique=True)


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="notes")
    op.drop_column("notes", "client_request_id")
