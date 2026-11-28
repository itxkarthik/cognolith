from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection, text
from sqlmodel import Session, col, select

from app.ai.chunking import NoteChunk
from app.ai.reranking import LexicalQuery
from app.core.config import settings
from app.models.chat import ChatGenerationStatus, ChatMessages, ChatRole, ChatSession
from app.models.document import Document, DocumentChunks
from app.models.embedding import EMBEDDING_TABLES, chunk_embeddings
from app.models.text_search import NOTE_CONFIG

# HNSW needs no training data, so unlike ivfflat it has good recall even when it is
# built on an empty table. ef_search is the candidate list size per query.
HNSW_EF_SEARCH = 100

_supports_iterative_scan: bool | None = None

REINDEX_HINT = (
    "Set EMBEDDING_DIMENSIONS to the embedding model's vector size and run "
    "`python -m scripts.reindex_embeddings` to rebuild the embedding tables."
)


class EmbeddingDimensionMismatchError(ValueError):
    """The embedding model's vector size differs from the stored embedding columns."""


def check_embedding_dimensions(embedding_dimensions: int) -> None:
    if embedding_dimensions <= 0:
        raise ValueError("Embedding dimensions must be greater than zero")
    if embedding_dimensions != settings.EMBEDDING_DIMENSIONS:
        raise EmbeddingDimensionMismatchError(
            f"The embedding model produced {embedding_dimensions}-dimensional vectors, but "
            f"the embedding tables store {settings.EMBEDDING_DIMENSIONS}. {REINDEX_HINT}"
        )


def stored_embedding_dimensions(connection: Connection) -> dict[str, int | None]:
    """Vector size of each embedding table's column; None when the table is missing."""
    names = [table.name for table in EMBEDDING_TABLES]
    rows = connection.execute(
        text(
            """
			SELECT c.relname AS table_name, a.atttypmod AS dimensions
			FROM pg_attribute a
			JOIN pg_class c ON c.oid = a.attrelid
			WHERE c.relname = ANY(CAST(:tables AS text[]))
			AND c.relkind = 'r'
			AND a.attname = 'embedding'
			AND NOT a.attisdropped
			"""
        ),
        {"tables": names},
    ).all()
    found: dict[str, int | None] = {name: None for name in names}
    for row in rows:
        found[str(row.table_name)] = int(row.dimensions)
    return found


@dataclass(slots=True)
class VectorSearchResult:
    chunk_id: int
    document_id: int
    chunk_index: int
    content: str
    score: float


@dataclass(slots=True)
class NoteVectorSearchResult:
    note_id: int
    title: str
    # The note's best-matching passage, not the whole note
    content: str
    score: float
    chunk_index: int


@dataclass(slots=True)
class LexicalChunkSearchResult:
    chunk_id: int
    document_id: int
    chunk_index: int
    content: str
    lexical_score: float
    exact_match: bool


@dataclass(slots=True)
class LexicalNoteSearchResult:
    note_id: int
    title: str
    content: str
    lexical_score: float
    exact_match: bool


@dataclass(slots=True)
class ChatVectorSearchResult:
    message_id: int
    session_id: int
    session_title: str | None
    role: str
    content: str
    score: float
    created_at: datetime | None
    updated_at: datetime | None


class PgVectorStore:
    def __init__(self, *, session: Session) -> None:
        self.session = session

    @staticmethod
    def _to_vector_literal(vector: Sequence[float]) -> str:
        return "[" + ",".join(str(float(value)) for value in vector) + "]"

    def ensure_schema(self, *, embedding_dimensions: int) -> None:
        """
        Fail clearly when vectors don't fit the embedding columns.

        The tables are created by migrations at settings.EMBEDDING_DIMENSIONS and the
        stored size is checked at startup, so no query is needed here.
        """
        check_embedding_dimensions(embedding_dimensions)

    def _tune_vector_search(self) -> None:
        """Per-transaction HNSW settings for a filtered nearest-neighbour query."""
        global _supports_iterative_scan
        connection = self.session.connection()
        connection.execute(text(f"SET LOCAL hnsw.ef_search = {HNSW_EF_SEARCH}"))
        if _supports_iterative_scan is None:
            version = connection.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            ).scalar()
            _supports_iterative_scan = _version_at_least(str(version or "0"), (0, 8))
        if _supports_iterative_scan:
            # Keep scanning when the user/document filter discards candidates, instead
            # of returning fewer than top_k rows
            connection.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))

    def indexed_document_chunk_ids(self, *, user_id: int, model: str) -> set[int]:
        rows = (
            self.session.connection()
            .execute(
                text(
                    """
				SELECT chunk_id
				FROM chunk_embeddings
				WHERE user_id = :user_id AND model = :model
				"""
                ),
                parameters={"user_id": user_id, "model": model},
            )
            .all()
        )
        return {int(row.chunk_id) for row in rows}

    def unindexed_document_chunks(self, *, user_id: int, model: str) -> list[DocumentChunks]:
        """The user's chunks with no vector for `model`; indexed ones are never loaded."""
        indexed = (
            select(chunk_embeddings.c.chunk_id)
            .where(
                chunk_embeddings.c.chunk_id == DocumentChunks.id,
                chunk_embeddings.c.model == model,
            )
            .exists()
        )
        return list(
            self.session.exec(
                select(DocumentChunks)
                .join(Document, col(Document.id) == col(DocumentChunks.document_id))
                .where(
                    Document.user_id == user_id,
                    col(Document.is_deleted).is_(False),
                    ~indexed,
                )
                .order_by(col(DocumentChunks.id))
            ).all()
        )

    def note_embedding_hashes(self, *, user_id: int, model: str) -> dict[int, str]:
        rows = (
            self.session.connection()
            .execute(
                text(
                    """
				SELECT DISTINCT note_id, content_hash
				FROM note_embeddings
				WHERE user_id = :user_id AND model = :model
				"""
                ),
                parameters={"user_id": user_id, "model": model},
            )
            .all()
        )
        return {int(row.note_id): str(row.content_hash) for row in rows}

    def chat_embedding_hashes(self, *, user_id: int, model: str) -> dict[int, str]:
        rows = (
            self.session.connection()
            .execute(
                text(
                    """
				SELECT message_id, content_hash
				FROM chat_message_embeddings
				WHERE user_id = :user_id AND model = :model
				"""
                ),
                parameters={"user_id": user_id, "model": model},
            )
            .all()
        )
        return {int(row.message_id): str(row.content_hash) for row in rows}

    def active_chat_messages(self, *, user_id: int) -> list[ChatMessages]:
        return list(
            self.session.exec(
                select(ChatMessages)
                .join(ChatSession, col(ChatSession.id) == col(ChatMessages.session_id))
                .where(
                    ChatSession.user_id == user_id,
                    col(ChatMessages.role).in_([ChatRole.user, ChatRole.assistant]),
                    # A reply still streaming changes; it's indexed once it's done
                    col(ChatMessages.generation_status).is_distinct_from(
                        ChatGenerationStatus.streaming
                    ),
                )
            ).all()
        )

    def store_note_embeddings(
        self,
        *,
        chunks: Sequence[NoteChunk],
        embeddings: Sequence[Sequence[float]],
        user_id: int,
        model: str,
    ) -> None:
        """
        Replace the stored chunks of every note in `chunks` with these. Pass all of a
        note's chunks in one call: rows past its last chunk, left from a longer previous
        version, are removed.
        """
        if len(chunks) != len(embeddings):
            raise ValueError("Chunk count does not match embedding count")
        if not chunks:
            return

        dimensions = len(embeddings[0])
        if dimensions <= 0:
            raise ValueError("Embedding vectors cannot be empty")
        self.ensure_schema(embedding_dimensions=dimensions)

        values_clauses: list[str] = []
        params: dict[str, object] = {}
        for index, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
            if len(embedding) != dimensions:
                raise ValueError("All embedding vectors must use the same dimensions")
            prefix = f"n{index}"
            values_clauses.append(
                f"(:{prefix}_note_id, :{prefix}_chunk_index, :{prefix}_user_id, :{prefix}_model, "
                f":{prefix}_content_hash, :{prefix}_content, CAST(:{prefix}_embedding AS vector))"
            )
            params[f"{prefix}_note_id"] = chunk.note_id
            params[f"{prefix}_chunk_index"] = chunk.chunk_index
            params[f"{prefix}_user_id"] = user_id
            params[f"{prefix}_model"] = model
            params[f"{prefix}_content_hash"] = chunk.content_hash
            params[f"{prefix}_content"] = chunk.content
            params[f"{prefix}_embedding"] = self._to_vector_literal(embedding)

        # Upsert, then drop the rows past each note's new chunk count. Not delete-then-
        # insert: a concurrent re-index of the same note would insert rows this
        # transaction's delete can't see, and the insert would then fail on the key.
        connection = self.session.connection()
        connection.execute(
            text(
                f"""
				INSERT INTO note_embeddings
					(note_id, chunk_index, user_id, model, content_hash, content, embedding)
				VALUES {", ".join(values_clauses)}
				ON CONFLICT (note_id, chunk_index)
				DO UPDATE SET
					user_id = EXCLUDED.user_id,
					model = EXCLUDED.model,
					content_hash = EXCLUDED.content_hash,
					content = EXCLUDED.content,
					embedding = EXCLUDED.embedding,
					updated_at = NOW()
				"""
            ),
            parameters=params,
        )
        chunk_counts: dict[int, int] = {}
        for chunk in chunks:
            chunk_counts[chunk.note_id] = max(chunk_counts.get(chunk.note_id, 0), chunk.chunk_index + 1)
        note_ids = sorted(chunk_counts)
        connection.execute(
            text(
                """
				DELETE FROM note_embeddings ne
				USING unnest(CAST(:note_ids AS int[]), CAST(:counts AS int[])) AS kept(note_id, chunk_count)
				WHERE ne.note_id = kept.note_id AND ne.chunk_index >= kept.chunk_count
				"""
            ),
            parameters={"note_ids": note_ids, "counts": [chunk_counts[i] for i in note_ids]},
        )

    def remove_note_embeddings(self, *, note_ids: Collection[int]) -> None:
        if not note_ids:
            return
        self.session.connection().execute(
            text("DELETE FROM note_embeddings WHERE note_id = ANY(CAST(:note_ids AS int[]))"),
            parameters={"note_ids": sorted(note_ids)},
        )

    def store_chat_message_embeddings(
        self,
        *,
        messages: Sequence[tuple[int, int, str]],
        embeddings: Sequence[Sequence[float]],
        user_id: int,
        model: str,
    ) -> None:
        if len(messages) != len(embeddings):
            raise ValueError("Chat message count does not match embedding count")
        if not messages:
            return

        dimensions = len(embeddings[0])
        if dimensions <= 0:
            raise ValueError("Embedding vectors cannot be empty")
        self.ensure_schema(embedding_dimensions=dimensions)

        values_clauses: list[str] = []
        params: dict[str, object] = {}
        for index, ((message_id, session_id, content_hash), embedding) in enumerate(
            zip(messages, embeddings)
        ):
            if len(embedding) != dimensions:
                raise ValueError("All embedding vectors must use the same dimensions")
            prefix = f"m{index}"
            values_clauses.append(
                f"(:{prefix}_message_id, :{prefix}_session_id, :{prefix}_user_id, "
                f":{prefix}_model, :{prefix}_content_hash, CAST(:{prefix}_embedding AS vector))"
            )
            params[f"{prefix}_message_id"] = message_id
            params[f"{prefix}_session_id"] = session_id
            params[f"{prefix}_user_id"] = user_id
            params[f"{prefix}_model"] = model
            params[f"{prefix}_content_hash"] = content_hash
            params[f"{prefix}_embedding"] = self._to_vector_literal(embedding)

        self.session.connection().execute(
            text(
                f"""
				INSERT INTO chat_message_embeddings
					(message_id, session_id, user_id, model, content_hash, embedding)
				VALUES {", ".join(values_clauses)}
				ON CONFLICT (message_id)
				DO UPDATE SET
					session_id = EXCLUDED.session_id,
					user_id = EXCLUDED.user_id,
					model = EXCLUDED.model,
					content_hash = EXCLUDED.content_hash,
					embedding = EXCLUDED.embedding,
					updated_at = NOW()
				"""
            ),
            parameters=params,
        )

    def upsert_chunk_embedding(
        self,
        *,
        chunk_id: int,
        document_id: int,
        user_id: int,
        embedding: Sequence[float],
        model: str,
    ) -> None:
        embedding_literal = self._to_vector_literal(embedding)

        self.session.connection().execute(
            text(
                """
				INSERT INTO chunk_embeddings (chunk_id, document_id, user_id, model, embedding)
				VALUES (:chunk_id, :document_id, :user_id, :model, CAST(:embedding AS vector))
				ON CONFLICT (chunk_id)
				DO UPDATE SET
					document_id = EXCLUDED.document_id,
					user_id = EXCLUDED.user_id,
					model = EXCLUDED.model,
					embedding = EXCLUDED.embedding,
					updated_at = NOW()
				"""
            ),
            parameters={
                "chunk_id": chunk_id,
                "document_id": document_id,
                "user_id": user_id,
                "model": model,
                "embedding": embedding_literal,
            },
        )

    def store_document_chunk_embeddings(
        self,
        *,
        chunks: Sequence[DocumentChunks],
        embeddings: Sequence[Sequence[float]],
        user_id: int,
        model: str,
    ) -> None:
        """
        Store multiple chunk embeddings efficiently using bulk insert.

        Performance improvements:
        - Uses a single INSERT ON CONFLICT statement instead of sequential upserts
        - Reduces database round trips from N to 1 (where N = number of chunks)
        - Significantly faster for documents with many chunks
        """
        if len(chunks) != len(embeddings):
            raise ValueError("Chunk count does not match embedding count")
        if not chunks:
            return

        first_embedding = embeddings[0]
        if not first_embedding:
            raise ValueError("Embedding vectors cannot be empty")

        dimensions = len(first_embedding)
        self.ensure_schema(embedding_dimensions=dimensions)

        # Validate all chunks and embeddings before bulk insert
        for chunk, embedding in zip(chunks, embeddings):
            if chunk.id is None or chunk.document_id is None:
                raise ValueError("Chunk must have persisted IDs before storing embeddings")
            if len(embedding) != dimensions:
                raise ValueError("All embedding vectors must use the same dimensions")

        # Build bulk insert statement with ON CONFLICT for upsert behavior
        # This is much more efficient than sequential upserts
        values_clauses = []
        params = {}

        for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            embedding_literal = self._to_vector_literal(embedding)
            param_prefix = f"c{idx}"

            values_clauses.append(
                f"(:{param_prefix}_chunk_id, :{param_prefix}_document_id, :{param_prefix}_user_id, "
                f":{param_prefix}_model, CAST(:{param_prefix}_embedding AS vector))"
            )
            params[f"{param_prefix}_chunk_id"] = chunk.id
            params[f"{param_prefix}_document_id"] = chunk.document_id
            params[f"{param_prefix}_user_id"] = user_id
            params[f"{param_prefix}_model"] = model
            params[f"{param_prefix}_embedding"] = embedding_literal

        values_sql = ", ".join(values_clauses)

        bulk_insert_statement = text(
            f"""
			INSERT INTO chunk_embeddings (chunk_id, document_id, user_id, model, embedding)
			VALUES {values_sql}
			ON CONFLICT (chunk_id)
			DO UPDATE SET
				document_id = EXCLUDED.document_id,
				user_id = EXCLUDED.user_id,
				model = EXCLUDED.model,
				embedding = EXCLUDED.embedding,
				updated_at = NOW()
			"""
        )

        self.session.connection().execute(bulk_insert_statement, params)

    def similarity_search(
        self,
        *,
        user_id: int,
        model: str,
        query_embedding: Sequence[float],
        top_k: int = 5,
        similarity_threshold: float | None = None,
        document_ids: Sequence[int] | None = None,
    ) -> list[VectorSearchResult]:
        if not query_embedding:
            return []

        self._tune_vector_search()
        embedding_literal = self._to_vector_literal(query_embedding)
        # Vectors from another model live in a different space even at equal dimensions
        where_clauses = ["ce.user_id = :user_id", "ce.model = :model"]
        params: dict[str, object] = {
            "user_id": user_id,
            "model": model,
            "embedding": embedding_literal,
            "top_k": max(1, top_k),
        }

        if similarity_threshold is not None:
            where_clauses.append(
                "(1 - (ce.embedding <=> CAST(:embedding AS vector))) >= :similarity_threshold"
            )
            params["similarity_threshold"] = similarity_threshold

        if document_ids:
            where_clauses.append("ce.document_id = ANY(CAST(:document_ids AS int[]))")
            params["document_ids"] = list(document_ids)

        statement = text(
            f"""
			SELECT
				dc.id AS chunk_id,
				dc.document_id AS document_id,
				dc.chunk_index AS chunk_index,
				dc.content AS content,
				(1 - (ce.embedding <=> CAST(:embedding AS vector))) AS score
			FROM chunk_embeddings ce
			INNER JOIN document_chunks dc ON dc.id = ce.chunk_id
			INNER JOIN documents d ON d.id = ce.document_id
			WHERE {" AND ".join(where_clauses)} AND d.is_deleted = FALSE
			ORDER BY ce.embedding <=> CAST(:embedding AS vector)
			LIMIT :top_k
			"""
        )

        rows = self.session.connection().execute(statement, params).all()
        return [
            VectorSearchResult(
                chunk_id=row.chunk_id,
                document_id=row.document_id,
                chunk_index=row.chunk_index,
                content=row.content,
                score=float(row.score),
            )
            for row in rows
        ]

    def note_similarity_search(
        self,
        *,
        user_id: int,
        model: str,
        query_embedding: Sequence[float],
        top_k: int = 5,
        similarity_threshold: float | None = None,
        note_ids: Sequence[int] | None = None,
    ) -> list[NoteVectorSearchResult]:
        if not query_embedding:
            return []

        embedding_literal = self._to_vector_literal(query_embedding)
        where_clauses = ["ne.user_id = :user_id", "ne.model = :model", "n.is_deleted = FALSE"]
        params: dict[str, object] = {
            "user_id": user_id,
            "model": model,
            "embedding": embedding_literal,
            "top_k": max(1, top_k),
        }
        if similarity_threshold is not None:
            where_clauses.append(
                "(1 - (ne.embedding <=> CAST(:embedding AS vector))) >= :similarity_threshold"
            )
            params["similarity_threshold"] = similarity_threshold
        if note_ids:
            where_clauses.append("n.id = ANY(CAST(:note_ids AS int[]))")
            params["note_ids"] = list(note_ids)

        # Each note's best passage, ranked. Exact over the user's note chunks rather than
        # an HNSW top-N: a long note with many close passages would fill a candidate list
        # and push other notes out, and a personal workspace has few enough notes to scan.
        rows = (
            self.session.connection()
            .execute(
                text(
                    f"""
				WITH best_per_note AS (
					SELECT DISTINCT ON (ne.note_id)
						ne.note_id,
						ne.chunk_index,
						ne.content,
						(1 - (ne.embedding <=> CAST(:embedding AS vector))) AS score
					FROM note_embeddings ne
					INNER JOIN notes n ON n.id = ne.note_id
					WHERE {" AND ".join(where_clauses)}
					ORDER BY ne.note_id, ne.embedding <=> CAST(:embedding AS vector)
				)
				SELECT b.note_id, n.title, b.chunk_index, b.content, b.score
				FROM best_per_note b
				INNER JOIN notes n ON n.id = b.note_id
				ORDER BY b.score DESC
				LIMIT :top_k
				"""
                ),
                parameters=params,
            )
            .all()
        )
        return [
            NoteVectorSearchResult(
                note_id=row.note_id,
                title=row.title,
                content=row.content,
                score=float(row.score),
                chunk_index=row.chunk_index,
            )
            for row in rows
        ]

    def lexical_chunk_search(
        self,
        *,
        user_id: int,
        query: LexicalQuery,
        top_k: int = 20,
        document_ids: Sequence[int] | None = None,
    ) -> list[LexicalChunkSearchResult]:
        if not query.phrase:
            return []

        where_clauses = ["d.user_id = :user_id", "d.is_deleted = FALSE"]
        params: dict[str, object] = {
            "user_id": user_id,
            "phrase": query.phrase,
            "phrase_pattern": f"%{query.phrase}%",
            "compact_pattern": f"%{query.compact_phrase}%",
            "top_k": max(1, top_k),
        }
        if document_ids:
            where_clauses.append("d.id = ANY(CAST(:document_ids AS int[]))")
            params["document_ids"] = list(document_ids)

        owner = " AND ".join(where_clauses)
        connection = self.session.connection()
        # The text search configs of this user's documents. Each gets its own condition
        # so the chunk vector index can be used (a per-row query config can't).
        configs = list(
            connection.execute(
                text(
                    f"SELECT DISTINCT text_search_config(d.language)::text FROM documents d "
                    f"WHERE {owner}"
                ),
                parameters=params,
            ).scalars()
        )
        if not configs:
            return []
        chunk_matches: list[str] = []
        for index, config in enumerate(configs):
            params[f"config_{index}"] = config
            query_config = f"CAST(:config_{index} AS regconfig)"
            chunk_matches.append(
                f"(dc.search_config = {query_config} AND "
                f"dc.search_vector @@ websearch_to_tsquery({query_config}, :phrase))"
            )

        rows = (
            connection.execute(
                text(
                    f"""
                    WITH candidates AS (
                        SELECT dc.id
                        FROM document_chunks dc
                        INNER JOIN documents d ON d.id = dc.document_id
                        WHERE {owner} AND ({" OR ".join(chunk_matches)})
                        UNION
                        SELECT dc.id
                        FROM document_chunks dc
                        INNER JOIN documents d ON d.id = dc.document_id
                        WHERE {owner} AND (
                            lower(dc.content) LIKE :phrase_pattern
                            OR lower(dc.content) LIKE :compact_pattern
                        )
                        UNION
                        -- A title match brings its document's first chunks; only
                        -- top_k can be returned, so no more are read
                        SELECT first_chunks.id
                        FROM documents d
                        CROSS JOIN LATERAL (
                            SELECT dc.id
                            FROM document_chunks dc
                            WHERE dc.document_id = d.id
                            ORDER BY dc.chunk_index
                            LIMIT :top_k
                        ) AS first_chunks
                        -- Through the user's documents: few, with stored title vectors
                        WHERE {owner} AND (
                            d.title_vector @@ websearch_to_tsquery(
                                text_search_config(d.language), :phrase
                            )
                            OR lower(d.title) LIKE :phrase_pattern
                            OR lower(d.title) LIKE :compact_pattern
                        )
                        UNION
                        -- Query words split between the title and the text: chunks
                        -- with any query word, in documents whose title has one,
                        -- that match the whole query together with the title
                        SELECT split_chunks.id
                        FROM documents d
                        CROSS JOIN LATERAL (
                            -- The query's lexemes, quoted so they aren't stemmed again
                            SELECT CAST(NULLIF(array_to_string(ARRAY(
                                SELECT quote_literal(lexeme)
                                FROM unnest(tsvector_to_array(
                                    to_tsvector(text_search_config(d.language), :phrase)
                                )) AS lexeme
                            ), ' | '), '') AS tsquery) AS any_word
                        ) AS words
                        CROSS JOIN LATERAL (
                            SELECT dc.id
                            FROM document_chunks dc
                            WHERE dc.document_id = d.id
                                AND dc.search_vector @@ words.any_word
                                AND (d.title_vector || dc.search_vector)
                                    @@ websearch_to_tsquery(dc.search_config, :phrase)
                            ORDER BY dc.chunk_index
                            LIMIT :top_k
                        ) AS split_chunks
                        WHERE {owner} AND d.title_vector @@ words.any_word
                    ),
                    lexical_matches AS (
                        SELECT
                            dc.id AS chunk_id,
                            dc.document_id,
                            dc.chunk_index,
                            dc.content,
                            (
                                lower(dc.content) LIKE :phrase_pattern
                                OR lower(dc.content) LIKE :compact_pattern
                                OR coalesce(lower(d.title), '') LIKE :phrase_pattern
                                OR coalesce(lower(d.title), '') LIKE :compact_pattern
                            ) AS exact_match,
                            ts_rank_cd(
                                d.title_vector || dc.search_vector,
                                websearch_to_tsquery(dc.search_config, :phrase)
                            ) AS text_rank
                        FROM candidates c
                        INNER JOIN document_chunks dc ON dc.id = c.id
                        INNER JOIN documents d ON d.id = dc.document_id
                    )
                    SELECT
                        chunk_id,
                        document_id,
                        chunk_index,
                        content,
                        exact_match,
                        CASE
                            WHEN exact_match THEN 1.0
                            ELSE LEAST(1.0, text_rank * 4.0)
                        END AS lexical_score
                    FROM lexical_matches
                    WHERE exact_match OR text_rank > 0
                    ORDER BY exact_match DESC, lexical_score DESC, chunk_id
                    LIMIT :top_k
                    """
                ),
                parameters=params,
            )
            .all()
        )
        return [
            LexicalChunkSearchResult(
                chunk_id=int(row.chunk_id),
                document_id=int(row.document_id),
                chunk_index=int(row.chunk_index),
                content=str(row.content),
                lexical_score=float(row.lexical_score),
                exact_match=bool(row.exact_match),
            )
            for row in rows
        ]

    def lexical_note_search(
        self,
        *,
        user_id: int,
        query: LexicalQuery,
        top_k: int = 20,
        note_ids: Sequence[int] | None = None,
    ) -> list[LexicalNoteSearchResult]:
        if not query.phrase:
            return []

        where_clauses = ["n.user_id = :user_id", "n.is_deleted = FALSE"]
        params: dict[str, object] = {
            "user_id": user_id,
            "phrase": query.phrase,
            "phrase_pattern": f"%{query.phrase}%",
            "compact_pattern": f"%{query.compact_phrase}%",
            "top_k": max(1, top_k),
        }
        if note_ids:
            where_clauses.append("n.id = ANY(CAST(:note_ids AS int[]))")
            params["note_ids"] = list(note_ids)

        rows = (
            self.session.connection()
            .execute(
                text(
                    f"""
                    WITH lexical_matches AS (
                        SELECT
                            n.id AS note_id,
                            n.title,
                            n.content,
                            (
                                coalesce(lower(n.title), '') LIKE :phrase_pattern
                                OR coalesce(lower(n.title), '') LIKE :compact_pattern
                                OR coalesce(lower(n.content), '') LIKE :phrase_pattern
                                OR coalesce(lower(n.content), '') LIKE :compact_pattern
                            ) AS exact_match,
                            ts_rank_cd(
                                n.search_vector,
                                websearch_to_tsquery('{NOTE_CONFIG}'::regconfig, :phrase)
                            ) AS text_rank
                        FROM notes n
                        -- Each condition has an index: the stored vector, or a trigram index
                        WHERE {" AND ".join(where_clauses)} AND (
                            n.search_vector @@ websearch_to_tsquery('{NOTE_CONFIG}'::regconfig, :phrase)
                            OR lower(n.title) LIKE :phrase_pattern
                            OR lower(n.title) LIKE :compact_pattern
                            OR lower(n.content) LIKE :phrase_pattern
                            OR lower(n.content) LIKE :compact_pattern
                        )
                    )
                    SELECT
                        note_id,
                        title,
                        content,
                        exact_match,
                        CASE
                            WHEN exact_match THEN 1.0
                            ELSE LEAST(1.0, text_rank * 4.0)
                        END AS lexical_score
                    FROM lexical_matches
                    WHERE exact_match OR text_rank > 0
                    ORDER BY exact_match DESC, lexical_score DESC, note_id
                    LIMIT :top_k
                    """
                ),
                parameters=params,
            )
            .all()
        )
        return [
            LexicalNoteSearchResult(
                note_id=int(row.note_id),
                title=str(row.title),
                content=row.content or "",
                lexical_score=float(row.lexical_score),
                exact_match=bool(row.exact_match),
            )
            for row in rows
        ]

    def chat_similarity_search(
        self,
        *,
        user_id: int,
        model: str,
        query_embedding: Sequence[float],
        top_k: int = 20,
        similarity_threshold: float | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[ChatVectorSearchResult]:
        if not query_embedding:
            return []

        self._tune_vector_search()
        embedding_literal = self._to_vector_literal(query_embedding)
        where_clauses = ["cme.user_id = :user_id", "cme.model = :model"]
        params: dict[str, object] = {
            "user_id": user_id,
            "model": model,
            "embedding": embedding_literal,
            "top_k": max(1, top_k),
        }
        if similarity_threshold is not None:
            where_clauses.append(
                "(1 - (cme.embedding <=> CAST(:embedding AS vector))) >= :similarity_threshold"
            )
            params["similarity_threshold"] = similarity_threshold
        if date_from is not None:
            where_clauses.append("cm.created_at >= :date_from")
            params["date_from"] = date_from
        if date_to is not None:
            where_clauses.append("cm.created_at <= :date_to")
            params["date_to"] = date_to

        rows = (
            self.session.connection()
            .execute(
                text(
                    f"""
				SELECT
					cm.id AS message_id,
					cs.id AS session_id,
					cs.title AS session_title,
					cm.role AS role,
					cm.content AS content,
					cm.created_at AS created_at,
					cm.updated_at AS updated_at,
					(1 - (cme.embedding <=> CAST(:embedding AS vector))) AS score
				FROM chat_message_embeddings cme
				INNER JOIN chat_messages cm ON cm.id = cme.message_id
				INNER JOIN chat_sessions cs ON cs.id = cme.session_id
				WHERE {" AND ".join(where_clauses)}
				ORDER BY cme.embedding <=> CAST(:embedding AS vector)
				LIMIT :top_k
				"""
                ),
                parameters=params,
            )
            .all()
        )
        return [
            ChatVectorSearchResult(
                message_id=int(row.message_id),
                session_id=int(row.session_id),
                session_title=row.session_title,
                role=str(row.role),
                content=str(row.content),
                score=float(row.score),
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]


def _version_at_least(version: str, minimum: tuple[int, int]) -> bool:
    parts: list[int] = []
    for piece in version.split(".")[:2]:
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 2:
        parts.append(0)
    return (parts[0], parts[1]) >= minimum
