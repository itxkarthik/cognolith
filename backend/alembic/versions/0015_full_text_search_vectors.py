"""store full-text search vectors and index them

Lexical search ran to_tsvector('english', title || ' ' || content) over every row on
every query: no index applied, a NULL title dropped the row, and documents were
stemmed as English whatever their language.

- text_search_config(language) maps an ISO 639-1 code to a Postgres config, or
  `simple` for codes without one
- document_chunks.search_vector and notes.search_vector are stored generated columns
  with GIN indexes; documents.title_vector is stored but not indexed, since a search
  reaches titles through the user's own documents. Documents and their chunks use
  the document's language; notes stay English (they have no language)
- document_chunks.search_config holds the document's config, set by a trigger on
  insert and when the document's language changes
- the expression indexes from the baseline, which no query matched, are dropped

Adding the generated columns rewrites the three tables.

Revision ID: 0015_full_text_search_vectors
Revises: 0014_note_client_request_id
Create Date: 2026-11-27 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015_full_text_search_vectors"
down_revision: str | Sequence[str] | None = "0014_note_client_request_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copies of app/models/text_search.py at this revision
_CONFIG_FUNCTION = """
CREATE OR REPLACE FUNCTION text_search_config(language text) RETURNS regconfig
LANGUAGE sql IMMUTABLE PARALLEL SAFE
RETURN CASE lower(split_part(coalesce(language, ''), '-', 1))
    WHEN 'ar' THEN 'arabic'::regconfig
    WHEN 'ca' THEN 'catalan'::regconfig
    WHEN 'da' THEN 'danish'::regconfig
    WHEN 'de' THEN 'german'::regconfig
    WHEN 'el' THEN 'greek'::regconfig
    WHEN 'en' THEN 'english'::regconfig
    WHEN 'es' THEN 'spanish'::regconfig
    WHEN 'eu' THEN 'basque'::regconfig
    WHEN 'fi' THEN 'finnish'::regconfig
    WHEN 'fr' THEN 'french'::regconfig
    WHEN 'ga' THEN 'irish'::regconfig
    WHEN 'hi' THEN 'hindi'::regconfig
    WHEN 'hu' THEN 'hungarian'::regconfig
    WHEN 'hy' THEN 'armenian'::regconfig
    WHEN 'id' THEN 'indonesian'::regconfig
    WHEN 'it' THEN 'italian'::regconfig
    WHEN 'lt' THEN 'lithuanian'::regconfig
    WHEN 'nb' THEN 'norwegian'::regconfig
    WHEN 'ne' THEN 'nepali'::regconfig
    WHEN 'nl' THEN 'dutch'::regconfig
    WHEN 'nn' THEN 'norwegian'::regconfig
    WHEN 'no' THEN 'norwegian'::regconfig
    WHEN 'pt' THEN 'portuguese'::regconfig
    WHEN 'ro' THEN 'romanian'::regconfig
    WHEN 'ru' THEN 'russian'::regconfig
    WHEN 'sr' THEN 'serbian'::regconfig
    WHEN 'sv' THEN 'swedish'::regconfig
    WHEN 'ta' THEN 'tamil'::regconfig
    WHEN 'tr' THEN 'turkish'::regconfig
    WHEN 'yi' THEN 'yiddish'::regconfig
    ELSE 'simple'::regconfig
END
"""

_CHUNK_CONFIG_TRIGGER = """
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

_DOCUMENT_LANGUAGE_TRIGGER = """
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

# (name, table, expression) of the baseline indexes no query used
_UNUSED_INDEXES = (
    (
        "ix_document_full_text",
        "documents",
        "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(content, '') "
        "|| ' ' || coalesce(summary, ''))",
    ),
    (
        "ix_document_search",
        "documents",
        "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(content, ''))",
    ),
    ("ix_document_chunks_content_search", "document_chunks", "to_tsvector('english', content)"),
    (
        "ix_notes_full_search",
        "notes",
        "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(content, '') "
        "|| ' ' || coalesce(summary, ''))",
    ),
    (
        "ix_notes_search",
        "notes",
        "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(content, ''))",
    ),
)


def upgrade() -> None:
    for name, _, _ in _UNUSED_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
    op.execute(_CONFIG_FUNCTION)

    op.execute(
        "ALTER TABLE documents ADD COLUMN title_vector tsvector GENERATED ALWAYS AS "
        "(to_tsvector(text_search_config(language), coalesce(title, ''))) STORED"
    )
    # Filled from each chunk's document before the vector is generated from it
    op.execute(
        "ALTER TABLE document_chunks "
        "ADD COLUMN search_config regconfig NOT NULL DEFAULT 'simple'::regconfig"
    )
    op.execute(
        "UPDATE document_chunks dc SET search_config = text_search_config(d.language) "
        "FROM documents d WHERE d.id = dc.document_id"
    )
    op.execute(
        "ALTER TABLE document_chunks ADD COLUMN search_vector tsvector GENERATED ALWAYS AS "
        "(to_tsvector(search_config, content)) STORED"
    )
    op.execute(
        "ALTER TABLE notes ADD COLUMN search_vector tsvector GENERATED ALWAYS AS "
        "(to_tsvector('english'::regconfig, coalesce(title, '') || ' ' || coalesce(content, ''))) STORED"
    )
    op.execute(_CHUNK_CONFIG_TRIGGER)
    op.execute(_DOCUMENT_LANGUAGE_TRIGGER)

    op.execute(
        "CREATE INDEX ix_document_chunks_search_vector ON document_chunks USING gin (search_vector)"
    )
    op.execute("CREATE INDEX ix_notes_search_vector ON notes USING gin (search_vector)")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS documents_language_search_config ON documents")
    op.execute("DROP TRIGGER IF EXISTS document_chunks_search_config ON document_chunks")
    op.execute("DROP FUNCTION IF EXISTS documents_sync_chunk_search_config()")
    op.execute("DROP FUNCTION IF EXISTS document_chunks_set_search_config()")
    # Dropping a column drops its index
    op.execute("ALTER TABLE notes DROP COLUMN IF EXISTS search_vector")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS search_vector")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS search_config")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS title_vector")
    op.execute("DROP FUNCTION IF EXISTS text_search_config(text)")
    for name, table, expression in _UNUSED_INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} USING gin (({expression}))")
