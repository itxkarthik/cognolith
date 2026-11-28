"""
Stored full-text search vectors for documents, their chunks and notes.

The vectors are generated columns, kept current by Postgres on every write and
indexed with GIN, so a lexical search reads the index instead of running
`to_tsvector` over every row. Documents are stemmed in their own language (the
`language` column, an ISO 639-1 code, mapped by `text_search_config`; unknown codes
fall back to `simple`, which only lower-cases). Notes have no language and stay
`english`. A chunk's generated column can't read its document's row, so a trigger
copies the document's config onto the chunk.

The columns are added to the tables but not mapped, so ORM loads never fetch them.
Migration 0015 creates the same objects in existing databases.
"""

from sqlalchemy import DDL, Column, Computed, Index, event, text
from sqlalchemy.dialects.postgresql import REGCONFIG, TSVECTOR
from sqlmodel import SQLModel

from .document import Document, DocumentChunks
from .note import Notes

# ISO 639-1 code -> the Postgres configuration that stems that language
LANGUAGE_CONFIGS = {
    "ar": "arabic",
    "ca": "catalan",
    "da": "danish",
    "de": "german",
    "el": "greek",
    "en": "english",
    "es": "spanish",
    "eu": "basque",
    "fi": "finnish",
    "fr": "french",
    "ga": "irish",
    "hi": "hindi",
    "hu": "hungarian",
    "hy": "armenian",
    "id": "indonesian",
    "it": "italian",
    "lt": "lithuanian",
    "nb": "norwegian",
    "ne": "nepali",
    "nl": "dutch",
    "nn": "norwegian",
    "no": "norwegian",
    "pt": "portuguese",
    "ro": "romanian",
    "ru": "russian",
    "sr": "serbian",
    "sv": "swedish",
    "ta": "tamil",
    "tr": "turkish",
    "yi": "yiddish",
}
NOTE_CONFIG = "english"


def _config_cases() -> str:
    return "\n".join(
        f"    WHEN '{code}' THEN '{config}'::regconfig" for code, config in LANGUAGE_CONFIGS.items()
    )


# A SQL-standard body is parsed once, when the function is created, so the regconfig
# literals are fixed OIDs and the function is truly immutable, as a generated column needs
CREATE_CONFIG_FUNCTION = f"""
CREATE OR REPLACE FUNCTION text_search_config(language text) RETURNS regconfig
LANGUAGE sql IMMUTABLE PARALLEL SAFE
RETURN CASE lower(split_part(coalesce(language, ''), '-', 1))
{_config_cases()}
    ELSE 'simple'::regconfig
END
"""

CREATE_CHUNK_CONFIG_TRIGGER = """
CREATE OR REPLACE FUNCTION document_chunks_set_search_config() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.search_config := coalesce(
        (SELECT text_search_config(language) FROM documents WHERE id = NEW.document_id),
        'simple'::regconfig
    );
    RETURN NEW;
END
$$;
CREATE OR REPLACE TRIGGER document_chunks_search_config
    BEFORE INSERT OR UPDATE OF document_id, search_config ON document_chunks
    FOR EACH ROW EXECUTE FUNCTION document_chunks_set_search_config();
"""

CREATE_DOCUMENT_LANGUAGE_TRIGGER = """
CREATE OR REPLACE FUNCTION documents_sync_chunk_search_config() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE document_chunks SET search_config = text_search_config(NEW.language)
    WHERE document_id = NEW.id;
    RETURN NULL;
END
$$;
CREATE OR REPLACE TRIGGER documents_language_search_config
    AFTER UPDATE OF language ON documents
    FOR EACH ROW WHEN (OLD.language IS DISTINCT FROM NEW.language)
    EXECUTE FUNCTION documents_sync_chunk_search_config();
"""

DOCUMENT_TITLE_VECTOR = "to_tsvector(text_search_config(language), coalesce(title, ''))"
CHUNK_SEARCH_VECTOR = "to_tsvector(search_config, content)"
NOTE_SEARCH_VECTOR = (
    f"to_tsvector('{NOTE_CONFIG}'::regconfig, coalesce(title, '') || ' ' || coalesce(content, ''))"
)


# Appended after the classes are mapped, so the ORM leaves these columns out
documents = Document.__table__  # pyright: ignore[reportAttributeAccessIssue]
chunks = DocumentChunks.__table__  # pyright: ignore[reportAttributeAccessIssue]
notes = Notes.__table__  # pyright: ignore[reportAttributeAccessIssue]

documents.append_column(
    Column("title_vector", TSVECTOR, Computed(DOCUMENT_TITLE_VECTOR, persisted=True))
)
chunks.append_column(
    Column(
        "search_config",
        REGCONFIG,
        nullable=False,
        server_default=text("'simple'::regconfig"),
    )
)
chunks.append_column(
    Column("search_vector", TSVECTOR, Computed(CHUNK_SEARCH_VECTOR, persisted=True))
)
notes.append_column(Column("search_vector", TSVECTOR, Computed(NOTE_SEARCH_VECTOR, persisted=True)))
Index("ix_document_chunks_search_vector", chunks.c.search_vector, postgresql_using="gin")
Index("ix_notes_search_vector", notes.c.search_vector, postgresql_using="gin")

event.listen(SQLModel.metadata, "before_create", DDL(CREATE_CONFIG_FUNCTION))
event.listen(chunks, "after_create", DDL(CREATE_CHUNK_CONFIG_TRIGGER))
event.listen(documents, "after_create", DDL(CREATE_DOCUMENT_LANGUAGE_TRIGGER))
event.listen(
    SQLModel.metadata,
    "after_drop",
    DDL(
        "DROP FUNCTION IF EXISTS document_chunks_set_search_config(), "
        "documents_sync_chunk_search_config(), text_search_config(text)"
    ),
)
