from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from difflib import SequenceMatcher
from typing import Any

from sqlmodel import Session, col, select

from app.ai.embeddings import generate_embedding, generate_embeddings
from app.ai.llm import LLMService, build_chat_messages
from app.ai.reranking import (
    LexicalQuery,
    RerankCandidate,
    RerankedCandidate,
    build_lexical_query,
    normalized_terms,
    rerank_candidates,
)
from app.ai.vectorstore import (
    LexicalChunkSearchResult,
    LexicalNoteSearchResult,
    NoteVectorSearchResult,
    PgVectorStore,
    VectorSearchResult,
)
from app.models.document import Document, DocumentChunks
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


@dataclass(frozen=True, slots=True)
class RetrievalContext:
    retrieval_query: str
    is_follow_up: bool
    prior_document_ids: tuple[int, ...]
    prior_note_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class RAGContextSource:
    citation_id: int
    source_type: str
    source_id: int
    title: str
    content: str
    vector_score: float | None
    hybrid_score: float | None
    chunk_id: int | None = None
    chunk_index: int | None = None
    chunk_end_index: int | None = None
    supporting_chunk_ids: tuple[int, ...] = ()
    origin: str = "vector"


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


def _resolve_retrieval_context(
    *,
    query: str,
    conversation_history: Sequence[dict[str, Any]] | None,
) -> RetrievalContext:
    normalized = _normalize_query(query)
    is_follow_up = _needs_history_for_retrieval(query) or bool(
        re.search(
            r"\b(?:more details?|the|this|that)\s+(?:project|document|note|one)s?\b",
            normalized,
        )
    )
    if not is_follow_up:
        return RetrievalContext(query, False, (), ())

    history = list(conversation_history or [])
    prior_document_ids: tuple[int, ...] = ()
    prior_note_ids: tuple[int, ...] = ()
    for message in reversed(history):
        if message.get("role") != "assistant":
            continue
        sources = message.get("sources")
        if not isinstance(sources, dict):
            continue
        documents = sources.get("documents")
        notes = sources.get("notes")
        document_ids = (
            tuple(
                int(item["document_id"])
                for item in documents
                if isinstance(item, dict) and isinstance(item.get("document_id"), int)
            )
            if isinstance(documents, list)
            else ()
        )
        note_ids = (
            tuple(
                int(item["note_id"])
                for item in notes
                if isinstance(item, dict) and isinstance(item.get("note_id"), int)
            )
            if isinstance(notes, list)
            else ()
        )
        if document_ids or note_ids:
            prior_document_ids = tuple(dict.fromkeys(document_ids))
            prior_note_ids = tuple(dict.fromkeys(note_ids))
            break

    previous_subject = ""
    for message in reversed(history):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        lexical_query = build_lexical_query(content)
        if lexical_query.phrase:
            previous_subject = lexical_query.phrase
            break

    retrieval_query = f"{previous_subject}\n{query}" if previous_subject else query
    return RetrievalContext(
        retrieval_query=retrieval_query,
        is_follow_up=True,
        prior_document_ids=prior_document_ids,
        prior_note_ids=prior_note_ids,
    )


def _generate_general_response(
    *,
    session: Session,
    user_id: int,
    query: str,
    conversation_history: Sequence[dict[str, Any]] | None,
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
    conversation_history: Sequence[dict[str, Any]] | None = None,
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

    retrieval_context = _resolve_retrieval_context(
        query=query,
        conversation_history=conversation_history,
    )
    retrieval_query = retrieval_context.retrieval_query

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
    retrieval_limit = max(20, top_k * 4)

    vector_store = PgVectorStore(session=session)
    vector_store.ensure_schema(embedding_dimensions=len(query_embedding))
    ensure_workspace_embeddings(
        session=session,
        vector_store=vector_store,
        user_id=user_id,
        embedding_model=embedding_model,
    )

    lexical_query = build_lexical_query(retrieval_query)
    has_prior_scope = bool(retrieval_context.prior_document_ids or retrieval_context.prior_note_ids)
    context_sources = _search_ranked_sources(
        session=session,
        vector_store=vector_store,
        user_id=user_id,
        query_embedding=query_embedding,
        query=retrieval_query,
        lexical_query=lexical_query,
        retrieval_limit=retrieval_limit,
        similarity_threshold=similarity_threshold,
        limit=top_k,
        document_ids=(retrieval_context.prior_document_ids if has_prior_scope else None),
        note_ids=(retrieval_context.prior_note_ids if has_prior_scope else None),
        prior_document_ids=set(retrieval_context.prior_document_ids),
        prior_note_ids=set(retrieval_context.prior_note_ids),
    )
    if not context_sources and has_prior_scope:
        context_sources = _search_ranked_sources(
            session=session,
            vector_store=vector_store,
            user_id=user_id,
            query_embedding=query_embedding,
            query=retrieval_query,
            lexical_query=lexical_query,
            retrieval_limit=retrieval_limit,
            similarity_threshold=similarity_threshold,
            limit=top_k,
            document_ids=None,
            note_ids=None,
            prior_document_ids=set(retrieval_context.prior_document_ids),
            prior_note_ids=set(retrieval_context.prior_note_ids),
        )

    inventory_entries = (
        _load_workspace_inventory(session=session, user_id=user_id) if needs_inventory else []
    )

    context_sources = _append_inventory_sources(
        sources=context_sources,
        inventory_entries=inventory_entries,
    )
    context_sources = _expand_document_context_sources(
        session=session,
        sources=context_sources,
    )

    if not context_sources:
        return _generate_general_response(
            session=session,
            user_id=user_id,
            query=query,
            conversation_history=conversation_history,
            casual=False,
        )

    context_chunks = _format_citation_context(context_sources)

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
        "repeat the raw context. Every factual claim taken from workspace context must end with "
        "the matching numeric citation marker, such as [1]. Use only source numbers present in "
        "the reference context. Do not cite general-knowledge or conversational statements."
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

    cited_ids = _extract_citation_ids(
        answer,
        valid_ids={source.citation_id for source in context_sources},
    )
    if not cited_ids:
        cited_ids = _infer_citation_ids(answer, sources=context_sources)
        answer = _insert_inferred_citations(
            answer,
            sources=context_sources,
            cited_ids=cited_ids,
        )
    sources = _build_cited_sources_payload(sources=context_sources, cited_ids=cited_ids)
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
        description = (
            document.content
            or document.summary
            or document.content_preview
            or "No extracted content available."
        )
        entries.append(
            WorkspaceInventoryEntry(
                source_type="document",
                source_id=document.id,
                title=document.title,
                description=description,
            )
        )
    for note in notes:
        if note.id is None:
            continue
        description = (
            note.content or note.summary or note.content_preview or "No content available."
        )
        entries.append(
            WorkspaceInventoryEntry(
                source_type="note",
                source_id=note.id,
                title=note.title,
                description=description,
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


def _format_citation_context(sources: Sequence[RAGContextSource]) -> list[str]:
    context_chunks: list[str] = []
    for source in sources:
        label = "Document" if source.source_type == "document" else "Note"
        if source.chunk_index is None:
            chunk_label = ""
        elif source.chunk_end_index is not None and source.chunk_end_index != source.chunk_index:
            chunk_label = f" | Chunks #{source.chunk_index}-#{source.chunk_end_index}"
        else:
            chunk_label = f" | Chunk #{source.chunk_index}"
        context_chunks.append(
            f"[Source {source.citation_id} | {label}: {source.title}{chunk_label}]\n"
            f"{source.content}"
        )
    return context_chunks


def _merge_overlapping_content(parts: Sequence[str]) -> str:
    if not parts:
        return ""
    merged = parts[0]
    for part in parts[1:]:
        overlap = 0
        maximum = min(len(merged), len(part), 500)
        for size in range(maximum, 9, -1):
            if merged.endswith(part[:size]):
                overlap = size
                break
        separator = "" if overlap else "\n"
        merged = f"{merged}{separator}{part[overlap:]}"
    return merged


def _expand_document_context_sources(
    *,
    session: Session,
    sources: Sequence[RAGContextSource],
    max_chars: int = 24000,
) -> list[RAGContextSource]:
    expanded: list[RAGContextSource] = []
    used_ranges: dict[int, list[tuple[int, int]]] = {}
    consumed_chars = 0

    for source in sources:
        expanded_source = source
        chunk_index = source.chunk_index
        if source.source_type == "document" and chunk_index is not None:
            start_index = max(0, chunk_index - 1)
            end_index = chunk_index + 1
            ranges = used_ranges.setdefault(source.source_id, [])
            if any(
                start_index <= used_end and end_index >= used_start
                for used_start, used_end in ranges
            ):
                continue
            chunks = session.exec(
                select(DocumentChunks)
                .where(
                    DocumentChunks.document_id == source.source_id,
                    col(DocumentChunks.chunk_index) >= start_index,
                    col(DocumentChunks.chunk_index) <= end_index,
                )
                .order_by(col(DocumentChunks.chunk_index).asc())
            ).all()
            if chunks:
                chunk_ids = tuple(chunk.id for chunk in chunks if chunk.id is not None)
                first_index = chunks[0].chunk_index
                last_index = chunks[-1].chunk_index
                expanded_source = replace(
                    source,
                    content=_merge_overlapping_content([chunk.content for chunk in chunks]),
                    chunk_index=first_index,
                    chunk_end_index=last_index,
                    supporting_chunk_ids=chunk_ids,
                )
                if first_index is not None and last_index is not None:
                    ranges.append((first_index, last_index))

        source_chars = len(expanded_source.content)
        if expanded and consumed_chars + source_chars > max_chars:
            continue
        if not expanded and source_chars > max_chars:
            expanded_source = replace(
                expanded_source,
                content=expanded_source.content[:max_chars].rstrip(),
            )
            source_chars = len(expanded_source.content)
        expanded.append(expanded_source)
        consumed_chars += source_chars

    return [replace(source, citation_id=index) for index, source in enumerate(expanded, start=1)]


def _extract_citation_ids(answer: str, *, valid_ids: set[int]) -> list[int]:
    citation_ids: list[int] = []
    seen: set[int] = set()
    for match in re.finditer(r"\[(\d+)\]", answer):
        citation_id = int(match.group(1))
        if citation_id not in valid_ids or citation_id in seen:
            continue
        citation_ids.append(citation_id)
        seen.add(citation_id)
    return citation_ids


def _normalized_phrase(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _infer_citation_ids(
    answer: str,
    *,
    sources: Sequence[RAGContextSource],
) -> list[int]:
    answer_phrase = _normalized_phrase(answer)
    answer_terms = normalized_terms(answer)
    if not answer_terms:
        return []

    cited_ids: list[int] = []
    for source in sources:
        title_phrase = _normalized_phrase(source.title)
        title_terms = normalized_terms(source.title)
        title_is_named = len(title_terms) >= 2 and title_phrase in answer_phrase
        source_terms = normalized_terms(f"{source.title} {source.content}")
        overlap_count = len(answer_terms.intersection(source_terms))
        answer_coverage = overlap_count / len(answer_terms)
        content_supports_answer = overlap_count >= 3 and answer_coverage >= 0.30
        if title_is_named or content_supports_answer:
            cited_ids.append(source.citation_id)
    return cited_ids


def _insert_inferred_citations(
    answer: str,
    *,
    sources: Sequence[RAGContextSource],
    cited_ids: Sequence[int],
) -> str:
    source_map = {source.citation_id: source for source in sources}
    enriched = answer
    trailing_ids: list[int] = []
    for citation_id in cited_ids:
        source = source_map.get(citation_id)
        if source is None:
            continue
        title_pattern = re.compile(re.escape(source.title), flags=re.IGNORECASE)
        if title_pattern.search(enriched):
            enriched = title_pattern.sub(
                lambda match: f"{match.group(0)} [{citation_id}]",
                enriched,
                count=1,
            )
        else:
            trailing_ids.append(citation_id)

    if trailing_ids:
        markers = " ".join(f"[{citation_id}]" for citation_id in trailing_ids)
        enriched = f"{enriched.rstrip()} {markers}"
    return enriched


def _search_ranked_sources(
    *,
    session: Session,
    vector_store: PgVectorStore,
    user_id: int,
    query_embedding: Sequence[float],
    query: str,
    lexical_query: LexicalQuery,
    retrieval_limit: int,
    similarity_threshold: float,
    limit: int,
    document_ids: Sequence[int] | None,
    note_ids: Sequence[int] | None,
    prior_document_ids: set[int],
    prior_note_ids: set[int],
) -> list[RAGContextSource]:
    chunk_hits = (
        vector_store.similarity_search(
            user_id=user_id,
            query_embedding=query_embedding,
            top_k=retrieval_limit,
            similarity_threshold=None,
            document_ids=document_ids,
        )
        if document_ids is None or document_ids
        else []
    )
    note_hits = (
        vector_store.note_similarity_search(
            user_id=user_id,
            query_embedding=query_embedding,
            top_k=retrieval_limit,
            similarity_threshold=None,
            note_ids=note_ids,
        )
        if note_ids is None or note_ids
        else []
    )
    lexical_chunk_hits = (
        vector_store.lexical_chunk_search(
            user_id=user_id,
            query=lexical_query,
            top_k=retrieval_limit,
            document_ids=document_ids,
        )
        if document_ids is None or document_ids
        else []
    )
    lexical_note_hits = (
        vector_store.lexical_note_search(
            user_id=user_id,
            query=lexical_query,
            top_k=retrieval_limit,
            note_ids=note_ids,
        )
        if note_ids is None or note_ids
        else []
    )
    document_map = _load_document_map(
        session=session,
        document_ids=[
            *[item.document_id for item in chunk_hits],
            *[item.document_id for item in lexical_chunk_hits],
        ],
    )
    return _rerank_vector_sources(
        query=query,
        chunk_hits=chunk_hits,
        note_hits=note_hits,
        lexical_chunk_hits=lexical_chunk_hits,
        lexical_note_hits=lexical_note_hits,
        document_map=document_map,
        similarity_threshold=similarity_threshold,
        limit=limit,
        prior_document_ids=prior_document_ids,
        prior_note_ids=prior_note_ids,
    )


def _rerank_vector_sources(
    *,
    query: str,
    chunk_hits: Sequence[VectorSearchResult],
    note_hits: Sequence[NoteVectorSearchResult],
    lexical_chunk_hits: Sequence[LexicalChunkSearchResult],
    lexical_note_hits: Sequence[LexicalNoteSearchResult],
    document_map: dict[int, Document],
    similarity_threshold: float,
    limit: int,
    prior_document_ids: set[int],
    prior_note_ids: set[int],
) -> list[RAGContextSource]:
    candidates: list[RerankCandidate] = []
    chunk_lookup: dict[str, VectorSearchResult | LexicalChunkSearchResult] = {}
    note_lookup: dict[str, NoteVectorSearchResult | LexicalNoteSearchResult] = {}
    lexical_chunks = {hit.chunk_id: hit for hit in lexical_chunk_hits}
    lexical_notes = {hit.note_id: hit for hit in lexical_note_hits}
    seen_chunks: set[int] = set()
    seen_notes: set[int] = set()

    for hit in chunk_hits:
        source_key = f"document:{hit.chunk_id}"
        document = document_map.get(hit.document_id)
        title = document.title if document else f"Document {hit.document_id}"
        lexical_hit = lexical_chunks.get(hit.chunk_id)
        candidates.append(
            RerankCandidate(
                source_key=source_key,
                source_type="document",
                source_id=hit.chunk_id,
                title=title,
                content=hit.content,
                vector_score=hit.score,
                lexical_score=lexical_hit.lexical_score if lexical_hit else 0.0,
                exact_match=lexical_hit.exact_match if lexical_hit else False,
                prior_source=hit.document_id in prior_document_ids,
            )
        )
        chunk_lookup[source_key] = hit
        seen_chunks.add(hit.chunk_id)

    for hit in lexical_chunk_hits:
        if hit.chunk_id in seen_chunks:
            continue
        source_key = f"document:{hit.chunk_id}"
        document = document_map.get(hit.document_id)
        title = document.title if document else f"Document {hit.document_id}"
        candidates.append(
            RerankCandidate(
                source_key=source_key,
                source_type="document",
                source_id=hit.chunk_id,
                title=title,
                content=hit.content,
                vector_score=None,
                lexical_score=hit.lexical_score,
                exact_match=hit.exact_match,
                prior_source=hit.document_id in prior_document_ids,
            )
        )
        chunk_lookup[source_key] = hit

    for hit in note_hits:
        source_key = f"note:{hit.note_id}"
        lexical_hit = lexical_notes.get(hit.note_id)
        candidates.append(
            RerankCandidate(
                source_key=source_key,
                source_type="note",
                source_id=hit.note_id,
                title=hit.title,
                content=hit.content,
                vector_score=hit.score,
                lexical_score=lexical_hit.lexical_score if lexical_hit else 0.0,
                exact_match=lexical_hit.exact_match if lexical_hit else False,
                prior_source=hit.note_id in prior_note_ids,
            )
        )
        note_lookup[source_key] = hit
        seen_notes.add(hit.note_id)

    for hit in lexical_note_hits:
        if hit.note_id in seen_notes:
            continue
        source_key = f"note:{hit.note_id}"
        candidates.append(
            RerankCandidate(
                source_key=source_key,
                source_type="note",
                source_id=hit.note_id,
                title=hit.title,
                content=hit.content,
                vector_score=None,
                lexical_score=hit.lexical_score,
                exact_match=hit.exact_match,
                prior_source=hit.note_id in prior_note_ids,
            )
        )
        note_lookup[source_key] = hit

    ranked = rerank_candidates(
        query=query,
        candidates=candidates,
        similarity_threshold=similarity_threshold,
        limit=limit,
        hybrid_score_window=0.10,
    )
    return [
        _context_source_from_ranked(
            citation_id=index,
            ranked=item,
            chunk_lookup=chunk_lookup,
            note_lookup=note_lookup,
            similarity_threshold=similarity_threshold,
        )
        for index, item in enumerate(ranked, start=1)
    ]


def _context_source_from_ranked(
    *,
    citation_id: int,
    ranked: RerankedCandidate,
    chunk_lookup: dict[str, VectorSearchResult | LexicalChunkSearchResult],
    note_lookup: dict[str, NoteVectorSearchResult | LexicalNoteSearchResult],
    similarity_threshold: float,
) -> RAGContextSource:
    if ranked.source_type == "document":
        hit = chunk_lookup[ranked.source_key]
        return RAGContextSource(
            citation_id=citation_id,
            source_type="document",
            source_id=hit.document_id,
            title=ranked.title,
            content=hit.content,
            vector_score=(
                ranked.vector_score
                if ranked.vector_score is not None and ranked.vector_score >= similarity_threshold
                else None
            ),
            hybrid_score=ranked.hybrid_score,
            chunk_id=hit.chunk_id,
            chunk_index=hit.chunk_index,
            origin=ranked.match_type,
        )

    hit = note_lookup[ranked.source_key]
    return RAGContextSource(
        citation_id=citation_id,
        source_type="note",
        source_id=hit.note_id,
        title=hit.title,
        content=hit.content,
        vector_score=(
            ranked.vector_score
            if ranked.vector_score is not None and ranked.vector_score >= similarity_threshold
            else None
        ),
        hybrid_score=ranked.hybrid_score,
        origin=ranked.match_type,
    )


def _append_inventory_sources(
    *,
    sources: Sequence[RAGContextSource],
    inventory_entries: Sequence[WorkspaceInventoryEntry],
) -> list[RAGContextSource]:
    combined = list(sources)
    existing_entities = {(source.source_type, source.source_id) for source in sources}
    next_citation_id = len(combined) + 1
    for entry in inventory_entries:
        entity_key = (entry.source_type, entry.source_id)
        if entity_key in existing_entities:
            continue
        combined.append(
            RAGContextSource(
                citation_id=next_citation_id,
                source_type=entry.source_type,
                source_id=entry.source_id,
                title=entry.title,
                content=entry.description,
                vector_score=None,
                hybrid_score=None,
                origin="inventory",
            )
        )
        existing_entities.add(entity_key)
        next_citation_id += 1
    return combined


def _build_cited_sources_payload(
    *,
    sources: Sequence[RAGContextSource],
    cited_ids: Sequence[int],
) -> dict[str, Any]:
    source_map = {source.citation_id: source for source in sources}
    documents: list[dict[str, Any]] = []
    document_map: dict[int, dict[str, Any]] = {}
    chunks: list[dict[str, Any]] = []
    notes: list[dict[str, Any]] = []

    for citation_id in cited_ids:
        source = source_map.get(citation_id)
        if source is None:
            continue

        if source.source_type == "document":
            document = document_map.get(source.source_id)
            if document is None:
                document = {
                    "document_id": source.source_id,
                    "title": source.title,
                    "chunk_count": 0,
                    "max_score": source.vector_score,
                    "citation_ids": [],
                    "origin": source.origin,
                }
                document_map[source.source_id] = document
                documents.append(document)
            document["citation_ids"].append(citation_id)
            if source.chunk_id is not None:
                document["chunk_count"] += max(1, len(source.supporting_chunk_ids))
                current_max = document["max_score"]
                if current_max is None or (
                    source.vector_score is not None and source.vector_score > current_max
                ):
                    document["max_score"] = source.vector_score
                chunks.append(
                    {
                        "chunk_id": source.chunk_id,
                        "document_id": source.source_id,
                        "document_title": source.title,
                        "chunk_index": source.chunk_index or 0,
                        "chunk_end_index": source.chunk_end_index,
                        "score": source.vector_score,
                        "hybrid_score": source.hybrid_score,
                        "preview": create_content_preview(source.content, max_length=200),
                        "citation_id": citation_id,
                        "origin": source.origin,
                    }
                )
            continue

        notes.append(
            {
                "note_id": source.source_id,
                "title": source.title,
                "score": source.vector_score,
                "hybrid_score": source.hybrid_score,
                "preview": create_content_preview(source.content, max_length=200),
                "citation_id": citation_id,
                "origin": source.origin,
            }
        )

    return {"documents": documents, "chunks": chunks, "notes": notes}


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
