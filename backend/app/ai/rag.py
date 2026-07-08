from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Any

from sqlmodel import Session, col, select

from app.ai.embeddings import generate_embedding, generate_embeddings
from app.ai.llm import LLMService, build_chat_messages
from app.ai.vectorstore import NoteVectorSearchResult, PgVectorStore, VectorSearchResult
from app.models.document import Document
from app.models.note import Notes
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
class RAGNoteSource:
    note_id: int
    title: str
    score: float
    preview: str


@dataclass(slots=True)
class RAGResult:
    answer: str
    sources: dict[str, Any]


@dataclass(slots=True)
class WorkspaceInventoryEntry:
    source_type: str
    source_id: int
    title: str
    description: str


_CASUAL_QUERIES = {
    "bye",
    "cool",
    "good afternoon",
    "good evening",
    "good morning",
    "goodbye",
    "great",
    "hello",
    "hello there",
    "hey",
    "hey there",
    "hi",
    "how are things",
    "how are you",
    "hows it going",
    "nice",
    "ok",
    "okay",
    "see you",
    "thank you",
    "thank you so much",
    "thanks",
    "what can you do",
    "what is up",
    "whats up",
    "who are you",
    "yo",
}


def _empty_sources() -> dict[str, list[Any]]:
    return {"documents": [], "chunks": [], "notes": []}


def _normalize_query(query: str) -> str:
    normalized = query.casefold().replace("’", "'").replace("'", "")
    return " ".join(re.sub(r"[^a-z0-9\s]", " ", normalized).split())


def _is_casual_conversation(query: str) -> bool:
    return _normalize_query(query) in _CASUAL_QUERIES


def _needs_history_for_retrieval(query: str) -> bool:
    normalized = _normalize_query(query)
    words = normalized.split()
    if len(words) > 10:
        return False

    follow_up_terms = {
        "it",
        "its",
        "that",
        "this",
        "they",
        "them",
        "their",
        "those",
        "these",
    }
    return bool(follow_up_terms.intersection(words)) or normalized.startswith(
        ("and ", "what about ", "how about ")
    )


def _generate_general_response(
    *,
    session: Session,
    user_id: int,
    query: str,
    conversation_history: Sequence[dict[str, str]] | None,
    casual: bool,
) -> RAGResult:
    if casual:
        system_prompt = (
            "You are Cognolith, a friendly, capable knowledge assistant. Respond to ordinary "
            "conversation naturally and briefly. Do not mention, quote, or summarize workspace "
            "documents unless the user explicitly asks about them. You can answer general "
            "questions and help users work with their notes and documents."
        )
    else:
        system_prompt = (
            "You are Cognolith, a helpful knowledge assistant with general knowledge. Answer general "
            "questions directly and naturally. If the user asks about their own notes, documents, "
            "projects, or personal facts and no workspace context is available, say you could not "
            "find that information rather than inventing it. Do not claim to cite or use documents "
            "that were not provided."
        )

    messages = build_chat_messages(
        user_prompt=query,
        system_prompt=system_prompt,
        conversation_history=(conversation_history or [])[-6:],
    )
    answer = _run_async(
        LLMService(session=session, user_id=user_id).generate_response(
            messages=messages,
            temperature=0.4,
            max_tokens=300,
        )
    )
    return RAGResult(answer=answer.strip(), sources=_empty_sources())


def run_rag_pipeline(
    *,
    session: Session,
    user_id: int,
    query: str,
    conversation_history: Sequence[dict[str, str]] | None = None,
) -> RAGResult:
    if not query.strip():
        return RAGResult(
            answer="Please provide a non-empty question.",
            sources=_empty_sources(),
        )

    query = query.strip()
    if _is_casual_conversation(query):
        return _generate_general_response(
            session=session,
            user_id=user_id,
            query=query,
            conversation_history=conversation_history,
            casual=True,
        )

    recent_user_context = [
        message["content"]
        for message in (conversation_history or [])[-4:]
        if message.get("role") == "user" and message.get("content")
    ]
    retrieval_query = (
        "\n".join([*recent_user_context, query]) if _needs_history_for_retrieval(query) else query
    )

    query_embedding, embedding_model = _run_async(
        generate_embedding(
            session=session,
            user_id=user_id,
            text=retrieval_query,
        )
    )

    user_settings = session.get(UserSettings, user_id)
    top_k = user_settings.top_k_results if user_settings else 5
    similarity_threshold = user_settings.similarity_threshold if user_settings else 0.7
    needs_inventory = _needs_workspace_inventory(retrieval_query)
    retrieval_limit = max(top_k, 12 if needs_inventory else 6)
    effective_threshold = (
        min(similarity_threshold, 0.4) if needs_inventory else similarity_threshold
    )

    vector_store = PgVectorStore(session=session)
    vector_store.ensure_schema(embedding_dimensions=len(query_embedding))
    ensure_workspace_embeddings(
        session=session,
        vector_store=vector_store,
        user_id=user_id,
        embedding_model=embedding_model,
    )

    chunk_hits = vector_store.similarity_search(
        user_id=user_id,
        query_embedding=query_embedding,
        top_k=retrieval_limit,
        similarity_threshold=effective_threshold,
    )
    note_hits = vector_store.note_similarity_search(
        user_id=user_id,
        query_embedding=query_embedding,
        top_k=retrieval_limit,
        similarity_threshold=effective_threshold,
    )

    adaptive_threshold = 0.4
    if not chunk_hits and not note_hits and effective_threshold > adaptive_threshold:
        chunk_hits = vector_store.similarity_search(
            user_id=user_id,
            query_embedding=query_embedding,
            top_k=retrieval_limit,
            similarity_threshold=adaptive_threshold,
        )
        note_hits = vector_store.note_similarity_search(
            user_id=user_id,
            query_embedding=query_embedding,
            top_k=retrieval_limit,
            similarity_threshold=adaptive_threshold,
        )

    ranked_hits = sorted(
        [(hit.score, "document", hit) for hit in chunk_hits]
        + [(hit.score, "note", hit) for hit in note_hits],
        key=lambda item: item[0],
        reverse=True,
    )
    if ranked_hits:
        score_window = 0.18 if needs_inventory else 0.12
        result_limit = min(retrieval_limit, 10 if needs_inventory else 6)
        relevance_floor = max(adaptive_threshold, ranked_hits[0][0] - score_window)
        ranked_hits = [item for item in ranked_hits if item[0] >= relevance_floor][:result_limit]
    ranked_chunk_hits: list[VectorSearchResult] = []
    ranked_note_hits: list[NoteVectorSearchResult] = []
    for _, source_type, hit in ranked_hits:
        if source_type == "document" and isinstance(hit, VectorSearchResult):
            ranked_chunk_hits.append(hit)
        elif source_type == "note" and isinstance(hit, NoteVectorSearchResult):
            ranked_note_hits.append(hit)
    chunk_hits = ranked_chunk_hits
    note_hits = ranked_note_hits

    inventory_entries = (
        _load_workspace_inventory(session=session, user_id=user_id) if needs_inventory else []
    )

    if not chunk_hits and not note_hits and not inventory_entries:
        return _generate_general_response(
            session=session,
            user_id=user_id,
            query=query,
            conversation_history=conversation_history,
            casual=False,
        )

    document_map = _load_document_map(
        session=session, document_ids=[item.document_id for item in chunk_hits]
    )
    context_chunks = _build_context_chunks(
        chunk_hits=chunk_hits,
        note_hits=note_hits,
        document_map=document_map,
    )
    if inventory_entries:
        context_chunks.insert(0, _format_workspace_inventory(inventory_entries))

    system_prompt = (
        "You are Cognolith, a knowledge assistant with normal conversational and general-knowledge "
        "ability. First decide whether the reference context is relevant to the current question. "
        "For questions about the user's workspace or personal information, use only relevant "
        "document and note context and never invent missing details. For ordinary conversation or "
        "general-knowledge questions, ignore irrelevant reference context and answer naturally. "
        "Do not preface answers with phrases such as 'Based on the provided document' unless the "
        "user asks for source attribution. Synthesize across relevant sources instead of relying on "
        "exact word overlap. For list, overview, comparison, or count questions, include all "
        "distinct supported items. Preserve exact names, codes, dates, and phrases, and do not "
        "repeat the raw context."
    )

    messages = build_chat_messages(
        user_prompt=query,
        context_chunks=context_chunks,
        system_prompt=system_prompt,
        conversation_history=(conversation_history or [])[-6:],
    )

    llm_service = LLMService(session=session, user_id=user_id)
    answer = _run_async(
        llm_service.generate_response(
            messages=messages,
            temperature=0.1,
            max_tokens=500 if needs_inventory else 300,
        )
    )
    answer = _repair_exact_terms(answer.strip(), context_chunks)

    sources = _build_sources_payload(
        chunk_hits=chunk_hits,
        note_hits=note_hits,
        document_map=document_map,
    )
    _merge_inventory_sources(sources=sources, inventory_entries=inventory_entries)
    return RAGResult(answer=answer, sources=sources)


_INVENTORY_SUBJECTS = (
    "project",
    "document",
    "note",
    "initiative",
    "plan",
    "topic",
    "item",
    "file",
)


def _needs_workspace_inventory(query: str) -> bool:
    normalized = " ".join(query.casefold().split())
    has_subject = any(
        re.search(rf"\b{re.escape(subject)}s?\b", normalized) for subject in _INVENTORY_SUBJECTS
    )
    if not has_subject:
        return False

    overview_phrases = (
        "what are",
        "which are",
        "what do i have",
        "list",
        "show me",
        "name",
        "overview",
        "summarize",
        "summarise",
        "compare",
        "how many",
        "all my",
        "all the",
        "each",
        "every",
    )
    return any(phrase in normalized for phrase in overview_phrases)


def _load_workspace_inventory(*, session: Session, user_id: int) -> list[WorkspaceInventoryEntry]:
    documents = session.exec(
        select(Document)
        .where(
            Document.user_id == user_id,
            col(Document.is_deleted).is_(False),
            Document.status == "completed",
        )
        .order_by(col(Document.updated_at).desc())
        .limit(40)
    ).all()
    notes = session.exec(
        select(Notes)
        .where(Notes.user_id == user_id, col(Notes.is_deleted).is_not(True))
        .order_by(col(Notes.updated_at).desc())
        .limit(40)
    ).all()

    entries: list[WorkspaceInventoryEntry] = []
    for document in documents:
        if document.id is None:
            continue
        description = document.summary or document.content_preview or "No summary available."
        entries.append(
            WorkspaceInventoryEntry(
                source_type="document",
                source_id=document.id,
                title=document.title,
                description=create_content_preview(description, max_length=700),
            )
        )
    for note in notes:
        if note.id is None:
            continue
        description = note.summary or note.content_preview or note.content
        entries.append(
            WorkspaceInventoryEntry(
                source_type="note",
                source_id=note.id,
                title=note.title,
                description=create_content_preview(description, max_length=700),
            )
        )
    return entries


def _format_workspace_inventory(
    entries: Sequence[WorkspaceInventoryEntry], *, max_chars: int = 18000
) -> str:
    lines = ["[Workspace inventory: use every relevant entry for overview questions]"]
    for entry in entries:
        label = "Document" if entry.source_type == "document" else "Note"
        line = f"- {label} #{entry.source_id}: {entry.title} - {entry.description}"
        if len("\n".join([*lines, line])) > max_chars:
            lines.append(
                "- Additional workspace entries were omitted because the context limit was reached."
            )
            break
        lines.append(line)
    return "\n".join(lines)


def _merge_inventory_sources(
    *, sources: dict[str, Any], inventory_entries: Sequence[WorkspaceInventoryEntry]
) -> None:
    existing_document_ids = {item["document_id"] for item in sources["documents"]}
    existing_note_ids = {item["note_id"] for item in sources["notes"]}

    for entry in inventory_entries:
        if entry.source_type == "document" and entry.source_id not in existing_document_ids:
            sources["documents"].append(
                {
                    "document_id": entry.source_id,
                    "title": entry.title,
                    "chunk_count": 0,
                    "max_score": 0.0,
                }
            )
        elif entry.source_type == "note" and entry.source_id not in existing_note_ids:
            sources["notes"].append(
                {
                    "note_id": entry.source_id,
                    "title": entry.title,
                    "score": 0.0,
                    "preview": create_content_preview(entry.description, max_length=200),
                }
            )


def _repair_exact_terms(answer: str, context_chunks: Sequence[str]) -> str:
    context = "\n".join(context_chunks)
    patterns = (
        re.compile(r"\b[A-Z][A-Z0-9-]{2,}(?:\s+[A-Z][A-Z0-9-]{2,})*\b"),
        re.compile(r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})+\b"),
    )

    source_terms = {match.group(0) for pattern in patterns for match in pattern.finditer(context)}
    repaired = answer
    for pattern in patterns:
        for match in list(pattern.finditer(repaired)):
            candidate = match.group(0)
            if candidate in source_terms:
                continue
            closest = max(
                source_terms,
                key=lambda source: SequenceMatcher(
                    None, candidate.casefold(), source.casefold()
                ).ratio(),
                default=None,
            )
            if closest is None:
                continue
            similarity = SequenceMatcher(None, candidate.casefold(), closest.casefold()).ratio()
            if similarity >= 0.82:
                repaired = repaired.replace(candidate, closest)

    return repaired


def _build_context_chunks(
    *,
    chunk_hits: list[VectorSearchResult],
    note_hits: list[NoteVectorSearchResult],
    document_map: dict[int, Document],
) -> list[str]:
    context_chunks: list[str] = []
    for hit in chunk_hits:
        document = document_map.get(hit.document_id)
        document_title = document.title if document else f"Document {hit.document_id}"
        context_chunks.append(
            f"[Document: {document_title} | Chunk #{hit.chunk_index} | score={hit.score:.3f}]\n{hit.content}"
        )
    for hit in note_hits:
        context_chunks.append(f"[Note: {hit.title} | score={hit.score:.3f}]\n{hit.content[:6000]}")
    return context_chunks


def ensure_workspace_embeddings(
    *,
    session: Session,
    vector_store: PgVectorStore,
    user_id: int,
    embedding_model: str,
    include_documents: bool = True,
    include_notes: bool = True,
    include_chats: bool = False,
) -> None:
    if include_documents:
        indexed_chunk_ids = vector_store.indexed_document_chunk_ids(
            user_id=user_id, model=embedding_model
        )
        missing_chunks = [
            chunk
            for chunk in vector_store.active_document_chunks(user_id=user_id)
            if chunk.id is not None and chunk.id not in indexed_chunk_ids
        ]

        for start in range(0, len(missing_chunks), 32):
            batch = missing_chunks[start : start + 32]
            embeddings, _ = _run_async(
                generate_embeddings(
                    session=session,
                    user_id=user_id,
                    texts=[chunk.content for chunk in batch],
                    model=embedding_model,
                )
            )
            vector_store.store_document_chunk_embeddings(
                chunks=batch,
                embeddings=embeddings,
                user_id=user_id,
                model=embedding_model,
            )

    if include_notes:
        active_notes = session.exec(
            select(Notes).where(Notes.user_id == user_id, col(Notes.is_deleted).is_not(True))
        ).all()
        indexed_note_hashes = vector_store.note_embedding_hashes(
            user_id=user_id, model=embedding_model
        )
        stale_notes: list[tuple[int, str, str]] = []
        for note in active_notes:
            if note.id is None:
                continue
            embedding_text = f"{note.title}\n\n{note.content}"[:12000]
            content_hash = hashlib.sha256(embedding_text.encode("utf-8")).hexdigest()
            if indexed_note_hashes.get(note.id) != content_hash:
                stale_notes.append((note.id, embedding_text, content_hash))

        for start in range(0, len(stale_notes), 32):
            batch = stale_notes[start : start + 32]
            embeddings, _ = _run_async(
                generate_embeddings(
                    session=session,
                    user_id=user_id,
                    texts=[embedding_text for _, embedding_text, _ in batch],
                    model=embedding_model,
                )
            )
            vector_store.store_note_embeddings(
                notes=[(note_id, content_hash) for note_id, _, content_hash in batch],
                embeddings=embeddings,
                user_id=user_id,
                model=embedding_model,
            )

    if include_chats:
        indexed_chat_hashes = vector_store.chat_embedding_hashes(
            user_id=user_id, model=embedding_model
        )
        stale_messages: list[tuple[int, int, str, str]] = []
        for message in vector_store.active_chat_messages(user_id=user_id):
            if message.id is None or message.session_id is None:
                continue
            embedding_text = message.content[:12000]
            content_hash = hashlib.sha256(embedding_text.encode("utf-8")).hexdigest()
            if indexed_chat_hashes.get(message.id) != content_hash:
                stale_messages.append(
                    (message.id, message.session_id, embedding_text, content_hash)
                )

        for start in range(0, len(stale_messages), 32):
            batch = stale_messages[start : start + 32]
            embeddings, _ = _run_async(
                generate_embeddings(
                    session=session,
                    user_id=user_id,
                    texts=[embedding_text for _, _, embedding_text, _ in batch],
                    model=embedding_model,
                )
            )
            vector_store.store_chat_message_embeddings(
                messages=[
                    (message_id, session_id, content_hash)
                    for message_id, session_id, _, content_hash in batch
                ],
                embeddings=embeddings,
                user_id=user_id,
                model=embedding_model,
            )


def _load_document_map(*, session: Session, document_ids: list[int]) -> dict[int, Document]:
    unique_ids = sorted(set(document_ids))
    if not unique_ids:
        return {}
    documents = session.exec(select(Document).where(col(Document.id).in_(unique_ids))).all()
    return {document.id: document for document in documents if document.id is not None}


def _build_sources_payload(
    *,
    chunk_hits: list[VectorSearchResult],
    note_hits: list[NoteVectorSearchResult],
    document_map: dict[int, Document],
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
        document_summary.values(),
        key=lambda item: float(item["max_score"]),
        reverse=True,
    )

    return {
        "documents": documents,
        "chunks": [asdict(item) for item in chunks],
        "notes": [
            asdict(
                RAGNoteSource(
                    note_id=hit.note_id,
                    title=hit.title,
                    score=round(hit.score, 6),
                    preview=create_content_preview(hit.content, max_length=200),
                )
            )
            for hit in note_hits
        ],
    }


def _run_async(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(lambda: asyncio.run(coro))
        return future.result()
