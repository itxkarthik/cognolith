from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import text
from sqlmodel import Session

from app.models.document import DocumentChunks


@dataclass(slots=True)
class VectorSearchResult:
    chunk_id: int
    document_id: int
    chunk_index: int
    content: str
    score: float


class PgVectorStore:
    def __init__(self, *, session: Session) -> None:
        self.session = session

    @staticmethod
    def _to_vector_literal(vector: Sequence[float]) -> str:
        return "[" + ",".join(str(float(value)) for value in vector) + "]"

    def ensure_schema(self, *, embedding_dimensions: int) -> None:
        if embedding_dimensions <= 0:
            raise ValueError("Embedding dimensions must be greater than zero")

        self.session.exec(text("CREATE EXTENSION IF NOT EXISTS vector"))

        self.session.exec(
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

        self.session.exec(
            text(
                """
				CREATE INDEX IF NOT EXISTS ix_chunk_embeddings_user_document
				ON chunk_embeddings (user_id, document_id)
				"""
            )
        )

        self.session.exec(
            text(
                """
				CREATE INDEX IF NOT EXISTS ix_chunk_embeddings_embedding_cosine
				ON chunk_embeddings USING ivfflat (embedding vector_cosine_ops)
				WITH (lists = 100)
				"""
            )
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

        self.session.exec(
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
            params={
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
                raise ValueError(
                    "Chunk must have persisted IDs before storing embeddings"
                )
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

        self.session.exec(bulk_insert_statement, params=params)

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
			WHERE {" AND ".join(where_clauses)}
			ORDER BY ce.embedding <=> CAST(:embedding AS vector)
			LIMIT :top_k
			"""
        )

        rows = self.session.exec(statement, params=params).all()
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
