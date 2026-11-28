from typing import cast

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import String, inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel

from app.ai.vectorstore import stored_embedding_dimensions
from app.core.config import settings
from app.core.database import engine

PORTABLE_ID_TABLES = {
    "users",
    "note_templates",
    "notes",
    "note_folders",
    "note_tags",
    "note_links",
    "documents",
    "chat_sessions",
    "chat_messages",
}
BACKUP_TABLES = {
    "google_drive_connections",
    "oauth_states",
    "workspace_backups",
    "backup_schedules",
}


def _alembic_config() -> Config:
    config = Config("alembic.ini")
    config.set_main_option("script_location", "alembic")
    return config


def test_embedding_tables_is_the_migration_head() -> None:
    script = ScriptDirectory.from_config(_alembic_config())

    assert script.get_current_head() == "0016_multi_process_coordination"
    assert (
        script.get_revision("0016_multi_process_coordination").down_revision
        == "0015_full_text_search_vectors"
    )
    assert (
        script.get_revision("0015_full_text_search_vectors").down_revision
        == "0014_note_client_request_id"
    )
    assert script.get_revision("0014_note_client_request_id").down_revision == "0013_note_revision"
    assert script.get_revision("0013_note_revision").down_revision == (
        "0012_document_embedding_status"
    )
    assert (
        script.get_revision("0012_document_embedding_status").down_revision
        == "0011_note_chunk_embeddings"
    )
    assert (
        script.get_revision("0011_note_chunk_embeddings").down_revision
        == "0010_account_security"
    )
    assert (
        script.get_revision("0010_account_security").down_revision == "0009_embedding_tables"
    )
    assert (
        script.get_revision("0009_embedding_tables").down_revision
        == "0008_hnsw_embedding_indexes"
    )
    assert (
        script.get_revision("0008_hnsw_embedding_indexes").down_revision
        == "0007_refresh_token_families"
    )
    assert (
        script.get_revision("0007_refresh_token_families").down_revision
        == "0006_unique_google_drive_subject"
    )
    assert (
        script.get_revision("0006_unique_google_drive_subject").down_revision
        == "0005_google_drive_backup_foundation"
    )
    assert script.get_revision("0005_google_drive_backup_foundation").down_revision == "0004_streaming_chat"


def test_upgrade_creates_embedding_tables_at_the_configured_size() -> None:
    config = _alembic_config()
    SQLModel.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))

    command.upgrade(config, "head")

    with engine.connect() as connection:
        sizes = stored_embedding_dimensions(connection)
        index_names = {
            index["name"] for index in inspect(connection).get_indexes("chunk_embeddings")
        }
    assert sizes == {
        "chunk_embeddings": settings.EMBEDDING_DIMENSIONS,
        "note_embeddings": settings.EMBEDDING_DIMENSIONS,
        "chat_message_embeddings": settings.EMBEDDING_DIMENSIONS,
    }
    assert "ix_chunk_embeddings_embedding_hnsw" in index_names


def _seed_pre_backup_rows(connection: Connection) -> None:
    user_id = connection.execute(
        text(
            """
            INSERT INTO users (
                email, is_active, is_superuser, created_at, updated_at, hashed_password, is_verified, is_deleted
            ) VALUES (
                'backup@example.com', true, false, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'hashed-password', false, false
            ) RETURNING id
            """
        )
    ).scalar_one()
    folder_id = connection.execute(
        text(
            """
            INSERT INTO note_folders (
                created_at, updated_at, user_id, name, is_shared, is_archived, sort_order, is_deleted
            ) VALUES (
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :user_id, 'Folder', false, false, 0, false
            ) RETURNING id
            """
        ),
        {"user_id": user_id},
    ).scalar_one()
    connection.execute(
        text(
            """
            INSERT INTO documents (
                created_at, updated_at, user_id, title, file_name, file_path, file_size, file_type, mime_type,
                is_deleted, language, status, chunk_count, last_accessed_at
            ) VALUES (
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :user_id, 'Document', 'document.txt', 'uploads/document.txt',
                1, 'txt', 'text/plain', false, 'en', 'completed', 0, CURRENT_TIMESTAMP
            )
            """
        ),
        {"user_id": user_id},
    )
    chat_session_id = connection.execute(
        text(
            """
            INSERT INTO chat_sessions (
                created_at, updated_at, user_id, is_archived, is_pinned, last_message_at
            ) VALUES (
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :user_id, false, false, CURRENT_TIMESTAMP
            ) RETURNING id
            """
        ),
        {"user_id": user_id},
    ).scalar_one()
    first_note_id = connection.execute(
        text(
            """
            INSERT INTO notes (
                created_at, updated_at, user_id, folder_id, title, content, content_type, ai_generated,
                is_favorite, is_archived, is_pinned, version, is_public, is_locked, is_deleted,
                last_accessed_at, last_edited_at
            ) VALUES (
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :user_id, :folder_id, 'One', '', 'markdown', false,
                false, false, false, 1, false, false, false, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            ) RETURNING id
            """
        ),
        {"user_id": user_id, "folder_id": folder_id},
    ).scalar_one()
    second_note_id = connection.execute(
        text(
            """
            INSERT INTO notes (
                created_at, updated_at, user_id, folder_id, title, content, content_type, ai_generated,
                is_favorite, is_archived, is_pinned, version, is_public, is_locked, is_deleted,
                last_accessed_at, last_edited_at
            ) VALUES (
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :user_id, :folder_id, 'Two', '', 'markdown', false,
                false, false, false, 1, false, false, false, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            ) RETURNING id
            """
        ),
        {"user_id": user_id, "folder_id": folder_id},
    ).scalar_one()
    connection.execute(
        text(
            """
            INSERT INTO note_tags (user_id, name, created_at)
            VALUES (:user_id, 'Tag', CURRENT_TIMESTAMP)
            """
        ),
        {"user_id": user_id},
    )
    connection.execute(
        text(
            """
            INSERT INTO note_links (source_note_id, target_note_id, link_type, created_at)
            VALUES (:first_note_id, :second_note_id, 'related', CURRENT_TIMESTAMP)
            """
        ),
        {"first_note_id": first_note_id, "second_note_id": second_note_id},
    )
    connection.execute(
        text(
            """
            INSERT INTO chat_messages (created_at, updated_at, session_id, role, content)
            VALUES (CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :chat_session_id, 'user', 'Hello')
            """
        ),
        {"chat_session_id": chat_session_id},
    )


def test_google_drive_backup_upgrade_creates_schema() -> None:
    config = _alembic_config()

    SQLModel.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))

    command.upgrade(config, "0004_streaming_chat")
    with engine.begin() as connection:
        _seed_pre_backup_rows(connection)
    command.upgrade(config, "head")

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    assert BACKUP_TABLES.issubset(table_names)

    connection_columns = {
        column["name"]: column for column in inspector.get_columns("google_drive_connections")
    }
    connection_status_type = cast(String, connection_columns["status"]["type"])
    assert connection_status_type.length is not None
    assert connection_status_type.length >= len("reauthorization_required")
    connection_indexes = {
        index["name"]: index
        for index in inspector.get_indexes("google_drive_connections")
    }
    assert connection_indexes[
        "ix_google_drive_connections_google_subject"
    ]["unique"] is True
    backup_columns = {column["name"]: column for column in inspector.get_columns("workspace_backups")}
    assert backup_columns["backup_id"]["nullable"] is False
    assert backup_columns["operation_kind"]["nullable"] is False
    assert backup_columns["source_backup_id"]["nullable"] is True
    backup_indexes = {index["name"]: index for index in inspector.get_indexes("workspace_backups")}
    assert backup_indexes["ix_workspace_backups_backup_id"]["unique"] is True

    for table_name in PORTABLE_ID_TABLES:
        columns = {column["name"]: column for column in inspector.get_columns(table_name)}
        assert columns["portable_id"]["nullable"] is False
        indexes = {index["name"]: index for index in inspector.get_indexes(table_name)}
        assert indexes[f"ix_{table_name}_portable_id"]["unique"] is True
        with engine.connect() as connection:
            assert connection.execute(
                text(f"SELECT count(*) FROM {table_name} WHERE portable_id IS NULL")
            ).scalar_one() == 0

    command.downgrade(config, "0004_streaming_chat")

    inspector = inspect(engine)
    assert BACKUP_TABLES.isdisjoint(inspector.get_table_names())
    for table_name in PORTABLE_ID_TABLES:
        assert "portable_id" not in {column["name"] for column in inspector.get_columns(table_name)}

    with engine.connect() as connection:
        assert connection.execute(
            text(
                """
                SELECT character_maximum_length
                FROM information_schema.columns
                WHERE table_name = 'alembic_version' AND column_name = 'version_num'
                """
            )
        ).scalar_one() == 64
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0004_streaming_chat"


def test_google_drive_subject_migration_rejects_existing_duplicates() -> None:
    config = _alembic_config()
    SQLModel.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    command.upgrade(config, "0005_google_drive_backup_foundation")

    with engine.begin() as connection:
        user_ids = connection.execute(
            text(
                """
                INSERT INTO users (
                    portable_id, email, is_active, is_superuser, created_at,
                    updated_at, hashed_password, is_verified, is_deleted
                ) VALUES
                    (gen_random_uuid(), 'first-owner@example.com', true, false,
                     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'hashed', true, false),
                    (gen_random_uuid(), 'second-owner@example.com', true, false,
                     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'hashed', true, false)
                RETURNING id
                """
            )
        ).scalars().all()
        for index, user_id in enumerate(user_ids):
            connection.execute(
                text(
                    """
                    INSERT INTO google_drive_connections (
                        user_id, encrypted_refresh_token, google_subject,
                        google_email, granted_scopes, status, connected_at,
                        created_at, updated_at
                    ) VALUES (
                        :user_id, :token, 'duplicate-subject', :email,
                        '[]'::jsonb, 'connected', CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "user_id": user_id,
                    "token": b"encrypted",
                    "email": f"owner-{index}@example.com",
                },
            )

    with pytest.raises(RuntimeError, match="duplicate active Google subjects"):
        command.upgrade(config, "head")

    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            == "0005_google_drive_backup_foundation"
        )
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM google_drive_connections"))
        connection.execute(
            text(
                "DELETE FROM users WHERE email IN "
                "('first-owner@example.com', 'second-owner@example.com')"
            )
        )
    command.upgrade(config, "head")


def _insert_user(connection: Connection, email: str) -> None:
    connection.execute(
        text(
            """
            INSERT INTO users (
                portable_id, email, is_active, is_superuser, created_at,
                updated_at, hashed_password, is_verified, is_deleted
            ) VALUES (
                gen_random_uuid(), :email, true, false,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'hashed', true, false
            )
            """
        ),
        {"email": email},
    )


def test_account_security_migration_lowercases_emails() -> None:
    config = _alembic_config()
    SQLModel.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    command.upgrade(config, "0009_embedding_tables")
    with engine.begin() as connection:
        _insert_user(connection, "Mixed.Case@Example.com")

    command.upgrade(config, "head")

    with engine.begin() as connection:
        assert connection.execute(text("SELECT email FROM users")).scalar_one() == (
            "mixed.case@example.com"
        )
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                _insert_user(connection, "MIXED.case@example.com")
        connection.execute(text("DELETE FROM users"))


def test_account_security_migration_rejects_case_duplicates() -> None:
    config = _alembic_config()
    SQLModel.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    command.upgrade(config, "0009_embedding_tables")
    with engine.begin() as connection:
        _insert_user(connection, "same@example.com")
        _insert_user(connection, "Same@Example.com")

    with pytest.raises(RuntimeError, match="differs only in letter case"):
        command.upgrade(config, "head")

    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "0009_embedding_tables"
        )
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM users"))
    command.upgrade(config, "head")


def _column_names(connection: Connection, table: str) -> set[str]:
    # Read from the catalog: reflecting the table warns on pgvector's vector type
    rows = connection.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name = :table"),
        {"table": table},
    )
    return {row.column_name for row in rows}


def test_note_chunk_migration_keys_note_embeddings_by_chunk() -> None:
    config = _alembic_config()
    SQLModel.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))

    command.upgrade(config, "head")
    with engine.connect() as connection:
        inspector = inspect(connection)
        columns = _column_names(connection, "note_embeddings")
        primary_key = inspector.get_pk_constraint("note_embeddings")["constrained_columns"]
    assert {"chunk_index", "content"} <= columns
    assert primary_key == ["note_id", "chunk_index"]

    command.downgrade(config, "0010_account_security")
    with engine.connect() as connection:
        inspector = inspect(connection)
        columns = _column_names(connection, "note_embeddings")
        primary_key = inspector.get_pk_constraint("note_embeddings")["constrained_columns"]
    assert not {"chunk_index", "content"} & columns
    assert primary_key == ["note_id"]
    command.upgrade(config, "head")


def _insert_document(connection: Connection, user_id: int, title: str, status: str) -> int:
    return connection.execute(
        text(
            """
            INSERT INTO documents (
                portable_id, created_at, updated_at, user_id, title, file_name, file_path,
                file_size, file_type, mime_type, is_deleted, language, status, chunk_count,
                last_accessed_at
            ) VALUES (
                gen_random_uuid(), NOW(), NOW(), :user_id, :title, 'f.txt', 'uploads/f.txt',
                1, 'txt', 'text/plain', false, 'en', :status, 1, NOW()
            ) RETURNING id
            """
        ),
        {"user_id": user_id, "title": title, "status": status},
    ).scalar_one()


def _insert_chunk(connection: Connection, document_id: int) -> int:
    return connection.execute(
        text(
            """
            INSERT INTO document_chunks
                (created_at, updated_at, document_id, chunk_index, content, vector_id)
            VALUES (NOW(), NOW(), :document_id, 0, 'text', 'v')
            RETURNING id
            """
        ),
        {"document_id": document_id},
    ).scalar_one()


def test_document_embedding_status_backfill_reflects_stored_vectors() -> None:
    config = _alembic_config()
    SQLModel.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    command.upgrade(config, "0011_note_chunk_embeddings")
    vector = "[" + ",".join(["1"] + ["0"] * (settings.EMBEDDING_DIMENSIONS - 1)) + "]"
    with engine.begin() as connection:
        _insert_user(connection, "backfill@example.com")
        user_id = connection.execute(text("SELECT id FROM users")).scalar_one()
        embedded = _insert_document(connection, user_id, "embedded", "completed")
        missing = _insert_document(connection, user_id, "missing", "completed")
        _insert_document(connection, user_id, "processing", "processing")
        _insert_chunk(connection, missing)
        connection.execute(
            text(
                """
                INSERT INTO chunk_embeddings (chunk_id, document_id, user_id, model, embedding)
                VALUES (:chunk_id, :document_id, :user_id, 'm', CAST(:vector AS vector))
                """
            ),
            {
                "chunk_id": _insert_chunk(connection, embedded),
                "document_id": embedded,
                "user_id": user_id,
                "vector": vector,
            },
        )

    command.upgrade(config, "head")

    with engine.begin() as connection:
        rows = connection.execute(
            text("SELECT title, embedding_status, processing_attempts FROM documents")
        ).all()
        assert {row.title: (row.embedding_status, row.processing_attempts) for row in rows} == {
            "embedded": ("indexed", 0),
            "missing": ("failed", 0),
            "processing": ("pending", 0),
        }
        connection.execute(text("DELETE FROM users"))


_UNUSED_FULL_TEXT_INDEXES = {
    "ix_document_full_text",
    "ix_document_search",
    "ix_document_chunks_content_search",
    "ix_notes_full_search",
    "ix_notes_search",
}


def _index_names(connection: Connection) -> set[str]:
    return set(connection.execute(text("SELECT indexname FROM pg_indexes")).scalars())


def test_full_text_migration_backfills_vectors_in_each_documents_language() -> None:
    config = _alembic_config()
    SQLModel.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    command.upgrade(config, "0014_note_client_request_id")
    with engine.begin() as connection:
        _insert_user(connection, "fulltext@example.com")
        user_id = connection.execute(text("SELECT id FROM users")).scalar_one()
        document_id = _insert_document(connection, user_id, "Häuser", "completed")
        connection.execute(text("UPDATE documents SET language = 'de-DE'"))
        _insert_chunk(connection, document_id)
        connection.execute(text("UPDATE document_chunks SET content = 'Die Häuser stehen'"))

    command.upgrade(config, "head")

    with engine.begin() as connection:
        assert not _UNUSED_FULL_TEXT_INDEXES & _index_names(connection)
        chunk = connection.execute(
            text(
                "SELECT search_config::text AS config, "
                "search_vector @@ to_tsquery('german', 'Haus') AS matches "
                "FROM document_chunks"
            )
        ).one()
        assert (chunk.config, chunk.matches) == ("german", True)
        assert connection.execute(
            text("SELECT title_vector @@ to_tsquery('german', 'Haus') FROM documents")
        ).scalar_one()

        # The triggers keep a chunk's config on its document's language
        connection.execute(text("UPDATE documents SET language = 'xx'"))
        _insert_chunk_at(connection, document_id, 1)
        assert set(
            connection.execute(text("SELECT search_config::text FROM document_chunks")).scalars()
        ) == {"simple"}
        connection.execute(text("DELETE FROM users"))

    command.downgrade(config, "0014_note_client_request_id")
    with engine.connect() as connection:
        assert _UNUSED_FULL_TEXT_INDEXES <= _index_names(connection)
        assert "search_vector" not in _column_names(connection, "notes")
        assert "search_config" not in _column_names(connection, "document_chunks")
    command.upgrade(config, "head")


def _insert_chunk_at(connection: Connection, document_id: int, chunk_index: int) -> None:
    connection.execute(
        text(
            """
            INSERT INTO document_chunks
                (created_at, updated_at, document_id, chunk_index, content, vector_id)
            VALUES (NOW(), NOW(), :document_id, :chunk_index, 'text', 'v')
            """
        ),
        {"document_id": document_id, "chunk_index": chunk_index},
    )
