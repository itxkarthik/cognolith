"""account security: case-insensitive emails, pending email, token version, delete rules

- Emails are lower-cased and a unique index on lower(email) stops two accounts
  differing only in case. The upgrade refuses to run if such accounts exist.
- users.pending_email holds a new address until its code is confirmed.
- users.token_version is embedded in access tokens; bumping it revokes them all.
- Foreign keys get ON DELETE rules so deleting an account removes its data:
  owned rows cascade, optional links are set to NULL.

Revision ID: 0010_account_security
Revises: 0009_embedding_tables
Create Date: 2026-11-26 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_account_security"
down_revision: str | Sequence[str] | None = "0009_embedding_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX_NAME = "ix_users_email_lower"

# (table, column, referenced table, ON DELETE action)
_DELETE_RULES: tuple[tuple[str, str, str, str], ...] = (
    ("activitylogs", "user_id", "users", "CASCADE"),
    ("backup_schedules", "user_id", "users", "CASCADE"),
    ("chat_sessions", "user_id", "users", "CASCADE"),
    ("documents", "user_id", "users", "CASCADE"),
    ("google_drive_connections", "user_id", "users", "CASCADE"),
    ("note_collaborators", "user_id", "users", "CASCADE"),
    ("note_folders", "user_id", "users", "CASCADE"),
    ("notes", "user_id", "users", "CASCADE"),
    ("note_tags", "user_id", "users", "CASCADE"),
    ("note_templates", "user_id", "users", "CASCADE"),
    ("oauth_states", "user_id", "users", "CASCADE"),
    ("refresh_tokens", "user_id", "users", "CASCADE"),
    ("user_settings", "user_id", "users", "CASCADE"),
    ("workspace_backups", "user_id", "users", "CASCADE"),
    ("chat_messages", "session_id", "chat_sessions", "CASCADE"),
    ("document_chunks", "document_id", "documents", "CASCADE"),
    ("note_collaborators", "note_id", "notes", "CASCADE"),
    ("note_links", "source_note_id", "notes", "CASCADE"),
    ("note_links", "target_note_id", "notes", "CASCADE"),
    ("note_tag_relations", "note_id", "notes", "CASCADE"),
    ("note_tag_relations", "tag_id", "note_tags", "CASCADE"),
    ("notes", "parent_note_id", "notes", "CASCADE"),
    ("note_folders", "parent_folder_id", "note_folders", "CASCADE"),
    ("notes", "locked_by", "users", "SET NULL"),
    ("notes", "folder_id", "note_folders", "SET NULL"),
    ("notes", "linked_document_id", "documents", "SET NULL"),
    ("notes", "linked_chat_session_id", "chat_sessions", "SET NULL"),
    ("notes", "previous_version_id", "notes", "SET NULL"),
    ("user_settings", "default_note_folder_id", "note_folders", "SET NULL"),
)


def _set_delete_rules(*, restore: bool) -> None:
    for table, column, referenced, action in _DELETE_RULES:
        name = f"{table}_{column}_fkey"
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(
            name, table, referenced, [column], ["id"], ondelete=None if restore else action
        )


def upgrade() -> None:
    duplicates = sa.text(
        "SELECT lower(email) FROM users GROUP BY lower(email) HAVING count(*) > 1 LIMIT 1"
    )
    duplicate = op.get_bind().execute(duplicates).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot make emails case-insensitive because several accounts share an "
            "address that differs only in letter case. Merge or remove the duplicate "
            "accounts, then rerun the migration."
        )
    op.execute("UPDATE users SET email = lower(email) WHERE email <> lower(email)")
    op.create_index(_INDEX_NAME, "users", [sa.text("lower(email)")], unique=True)
    op.add_column("users", sa.Column("pending_email", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    _set_delete_rules(restore=False)


def downgrade() -> None:
    _set_delete_rules(restore=True)
    op.drop_column("users", "token_version")
    op.drop_column("users", "pending_email")
    op.drop_index(_INDEX_NAME, table_name="users")
