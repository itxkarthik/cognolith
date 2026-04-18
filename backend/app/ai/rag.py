from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Any

from sqlmodel import Session, select

from app.ai.embeddings import generate_embedding
from app.ai.llm import LLMService, build_chat_messages
from app.ai.vectorstore import PgVectorStore, VectorSearchResult
from app.models.document import Document
from app.models.user import UserSettings
from app.utils.text_processing import create_content_preview


@dataclass(slots=True)
class RAGChunkSource:
    chunk_id: int
    document_id: int
    document_title: str
    chunk_index: int
    score: float
    preview: str


@dataclass(slots=True)
class RAGResult:
    answer: str
    sources: dict[str, Any]


def run_rag_pipeline(*, session: Session, user_id: int, query: str) -> RAGResult:
    if not query.strip():
        return RAGResult(
            answer="Please provide a non-empty question.", sources={"documents": [], "chunks": []}
        )

    query_embedding, _ = _run_async(
        generate_embedding(
            session=session,
            user_id=user_id,
            text=query,
        )
    )

    user_settings = session.get(UserSettings, user_id)
    top_k = user_settings.top_k_results if user_settings else 5
    similarity_threshold = user_settings.similarity_threshold if user_settings else 0.7

    vector_store = PgVectorStore(session=session)
    chunk_hits = vector_store.similarity_search(
        user_id=user_id,
        query_embedding=query_embedding,
        top_k=top_k,
        similarity_threshold=similarity_threshold,
    )

    if not chunk_hits:
        return RAGResult(
            answer="I couldn't find relevant document context for your question yet.",
            sources={"documents": [], "chunks": []},
        )

    document_map = _load_document_map(
        session=session, document_ids=[item.document_id for item in chunk_hits]
    )
    context_chunks = _build_context_chunks(chunk_hits=chunk_hits, document_map=document_map)

    system_prompt = (
        "You are a personal knowledge assistant. Answer using only the provided context. "
        "If context is insufficient, say so clearly and suggest what information is missing."
    )

    messages = build_chat_messages(
        user_prompt=query,
        context_chunks=context_chunks,
        system_prompt=system_prompt,
    )

    llm_service = LLMService(session=session, user_id=user_id)
    answer = _run_async(llm_service.generate_response(messages=messages))

    sources = _build_sources_payload(chunk_hits=chunk_hits, document_map=document_map)
    return RAGResult(answer=answer, sources=sources)


def _build_context_chunks(
    *, chunk_hits: list[VectorSearchResult], document_map: dict[int, Document]
) -> list[str]:
    context_chunks: list[str] = []
    for hit in chunk_hits:
        document = document_map.get(hit.document_id)
        document_title = document.title if document else f"Document {hit.document_id}"
        context_chunks.append(
            f"[Document: {document_title} | Chunk #{hit.chunk_index} | score={hit.score:.3f}]\n{hit.content}"
        )
    return context_chunks


def _load_document_map(*, session: Session, document_ids: list[int]) -> dict[int, Document]:
    unique_ids = sorted(set(document_ids))
    if not unique_ids:
        return {}
    documents = session.exec(select(Document).where(Document.id.in_(unique_ids))).all()
    return {document.id: document for document in documents if document.id is not None}


def _build_sources_payload(
    *, chunk_hits: list[VectorSearchResult], document_map: dict[int, Document]
) -> dict[str, Any]:
    chunks: list[RAGChunkSource] = []
    document_summary: dict[int, dict[str, Any]] = {}

    for hit in chunk_hits:
        document = document_map.get(hit.document_id)
        document_title = document.title if document else f"Document {hit.document_id}"

        chunk_source = RAGChunkSource(
            chunk_id=hit.chunk_id,
            document_id=hit.document_id,
            document_title=document_title,
            chunk_index=hit.chunk_index,
            score=round(hit.score, 6),
            preview=create_content_preview(hit.content, max_length=200),
        )
        chunks.append(chunk_source)

        summary = document_summary.setdefault(
            hit.document_id,
            {
                "document_id": hit.document_id,
                "title": document_title,
                "chunk_count": 0,
                "max_score": 0.0,
            },
        )
        summary["chunk_count"] += 1
        summary["max_score"] = max(float(summary["max_score"]), float(hit.score))

    documents = sorted(
        document_summary.values(), key=lambda item: float(item["max_score"]), reverse=True
    )

    return {
        "documents": documents,
        "chunks": [asdict(item) for item in chunks],
    }


def _run_async(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(lambda: asyncio.run(coro))
        return future.result()
