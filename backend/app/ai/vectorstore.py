from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlmodel import Session, col, select

from app.ai.reranking import LexicalQuery
from app.models.chat import ChatMessages, ChatRole, ChatSession
from app.models.document import Document, DocumentChunks


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
    content: str
    score: float


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
        if embedding_dimensions <= 0:
            raise ValueError("Embedding dimensions must be greater than zero")

        self.session.connection().execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        self.session.connection().execute(
            text(
                f"""
				CREATE TABLE IF NOT EXISTS chunk_embeddings (
					chunk_id INTEGER PRIMARY KEY REFERENCES document_chunks(id) ON DELETE CASCADE,
					document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
					user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
					model VARCHAR(100) NOT NULL,
					embedding vector({embedding_dimensions}) NOT NULL,
					created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
					updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
				)
				"""
            )
        )

        self.session.connection().execute(
            text(
                f"""
				CREATE TABLE IF NOT EXISTS note_embeddings (
					note_id INTEGER PRIMARY KEY REFERENCES notes(id) ON DELETE CASCADE,
					user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
					model VARCHAR(100) NOT NULL,
					content_hash VARCHAR(64) NOT NULL,
					embedding vector({embedding_dimensions}) NOT NULL,
					created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
					updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
				)
				"""
            )
        )

        self.session.connection().execute(
            text(
                f"""
				CREATE TABLE IF NOT EXISTS chat_message_embeddings (
					message_id INTEGER PRIMARY KEY REFERENCES chat_messages(id) ON DELETE CASCADE,
					session_id INTEGER NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
					user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
					model VARCHAR(100) NOT NULL,
					content_hash VARCHAR(64) NOT NULL,
					embedding vector({embedding_dimensions}) NOT NULL,
					created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
					updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
				)
				"""
            )
        )

        self.session.connection().execute(
            text(
                """
				CREATE INDEX IF NOT EXISTS ix_chunk_embeddings_user_document
				ON chunk_embeddings (user_id, document_id)
				"""
            )
        )

        self.session.connection().execute(
            text(
                """
				CREATE INDEX IF NOT EXISTS ix_chunk_embeddings_embedding_cosine
				ON chunk_embeddings USING ivfflat (embedding vector_cosine_ops)
				WITH (lists = 100)
				"""
            )
        )

        self.session.connection().execute(
            text(
                """
				CREATE INDEX IF NOT EXISTS ix_note_embeddings_user
				ON note_embeddings (user_id, note_id)
				"""
            )
        )

        self.session.connection().execute(
            text(
                """
				CREATE INDEX IF NOT EXISTS ix_note_embeddings_embedding_cosine
				ON note_embeddings USING ivfflat (embedding vector_cosine_ops)
				WITH (lists = 100)
				"""
            )
        )

        self.session.connection().execute(
            text(
                """
				CREATE INDEX IF NOT EXISTS ix_chat_message_embeddings_user_session
				ON chat_message_embeddings (user_id, session_id)
				"""
            )
        )

        self.session.connection().execute(
            text(
                """
				CREATE INDEX IF NOT EXISTS ix_chat_message_embeddings_embedding_cosine
				ON chat_message_embeddings USING ivfflat (embedding vector_cosine_ops)
				WITH (lists = 100)
				"""
            )
        )

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

    def active_document_chunks(self, *, user_id: int) -> list[DocumentChunks]:
        return list(
            self.session.exec(
                select(DocumentChunks)
                .join(Document, col(Document.id) == col(DocumentChunks.document_id))
                .where(Document.user_id == user_id, col(Document.is_deleted).is_(False))
            ).all()
        )

    def note_embedding_hashes(self, *, user_id: int, model: str) -> dict[int, str]:
        rows = (
            self.session.connection()
            .execute(
                text(
                    """
				SELECT note_id, content_hash
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
                )
            ).all()
        )

    def store_note_embeddings(
        self,
        *,
        notes: Sequence[tuple[int, str]],
        embeddings: Sequence[Sequence[float]],
        user_id: int,
        model: str,
    ) -> None:
        if len(notes) != len(embeddings):
            raise ValueError("Note count does not match embedding count")
        if not notes:
            return

        dimensions = len(embeddings[0])
        if dimensions <= 0:
            raise ValueError("Embedding vectors cannot be empty")
        self.ensure_schema(embedding_dimensions=dimensions)

        values_clauses: list[str] = []
        params: dict[str, object] = {}
        for index, ((note_id, content_hash), embedding) in enumerate(zip(notes, embeddings)):
            if len(embedding) != dimensions:
                raise ValueError("All embedding vectors must use the same dimensions")
            prefix = f"n{index}"
            values_clauses.append(
                f"(:{prefix}_note_id, :{prefix}_user_id, :{prefix}_model, "
                f":{prefix}_content_hash, CAST(:{prefix}_embedding AS vector))"
            )
            params[f"{prefix}_note_id"] = note_id
            params[f"{prefix}_user_id"] = user_id
            params[f"{prefix}_model"] = model
            params[f"{prefix}_content_hash"] = content_hash
            params[f"{prefix}_embedding"] = self._to_vector_literal(embedding)

        self.session.connection().execute(
            text(
                f"""
				INSERT INTO note_embeddings (note_id, user_id, model, content_hash, embedding)
				VALUES {", ".join(values_clauses)}
				ON CONFLICT (note_id)
				DO UPDATE SET
					user_id = EXCLUDED.user_id,
					model = EXCLUDED.model,
					content_hash = EXCLUDED.content_hash,
					embedding = EXCLUDED.embedding,
					updated_at = NOW()
				"""
            ),
            parameters=params,
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
        query_embedding: Sequence[float],
        top_k: int = 5,
        similarity_threshold: float | None = None,
        document_ids: Sequence[int] | None = None,
    ) -> list[VectorSearchResult]:
        if not query_embedding:
            return []

        embedding_literal = self._to_vector_literal(query_embedding)
        where_clauses = ["ce.user_id = :user_id"]
        params: dict[str, object] = {
            "user_id": user_id,
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
        query_embedding: Sequence[float],
        top_k: int = 5,
        similarity_threshold: float | None = None,
        note_ids: Sequence[int] | None = None,
    ) -> list[NoteVectorSearchResult]:
        if not query_embedding:
            return []

        embedding_literal = self._to_vector_literal(query_embedding)
        where_clauses = ["ne.user_id = :user_id", "n.is_deleted = FALSE"]
        params: dict[str, object] = {
            "user_id": user_id,
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

        rows = (
            self.session.connection()
            .execute(
                text(
                    f"""
				SELECT
					n.id AS note_id,
					n.title AS title,
					n.content AS content,
					(1 - (ne.embedding <=> CAST(:embedding AS vector))) AS score
				FROM note_embeddings ne
				INNER JOIN notes n ON n.id = ne.note_id
				WHERE {" AND ".join(where_clauses)}
				ORDER BY ne.embedding <=> CAST(:embedding AS vector)
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

        rows = (
            self.session.connection()
            .execute(
                text(
                    f"""
                    WITH lexical_matches AS (
                        SELECT
                            dc.id AS chunk_id,
                            dc.document_id,
                            dc.chunk_index,
                            dc.content,
                            (
                                lower(dc.content) LIKE :phrase_pattern
                                OR lower(dc.content) LIKE :compact_pattern
                                OR lower(d.title) LIKE :phrase_pattern
                                OR lower(d.title) LIKE :compact_pattern
                            ) AS exact_match,
                            ts_rank_cd(
                                to_tsvector('english', d.title || ' ' || dc.content),
                                websearch_to_tsquery('english', :phrase)
                            ) AS text_rank
                        FROM document_chunks dc
                        INNER JOIN documents d ON d.id = dc.document_id
                        WHERE {" AND ".join(where_clauses)}
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
                                lower(n.title) LIKE :phrase_pattern
                                OR lower(n.title) LIKE :compact_pattern
                                OR lower(n.content) LIKE :phrase_pattern
                                OR lower(n.content) LIKE :compact_pattern
                            ) AS exact_match,
                            ts_rank_cd(
                                to_tsvector('english', n.title || ' ' || n.content),
                                websearch_to_tsquery('english', :phrase)
                            ) AS text_rank
                        FROM notes n
                        WHERE {" AND ".join(where_clauses)}
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
                content=str(row.content),
                lexical_score=float(row.lexical_score),
                exact_match=bool(row.exact_match),
            )
            for row in rows
        ]

    def chat_similarity_search(
        self,
        *,
        user_id: int,
        query_embedding: Sequence[float],
        top_k: int = 20,
        similarity_threshold: float | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[ChatVectorSearchResult]:
        if not query_embedding:
            return []

        embedding_literal = self._to_vector_literal(query_embedding)
        where_clauses = ["cme.user_id = :user_id"]
        params: dict[str, object] = {
            "user_id": user_id,
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
