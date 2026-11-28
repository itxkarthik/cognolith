from sqlalchemy import text
from sqlmodel import Session

from app.ai.rag import RAGContextSource, _expand_document_context_sources
from app.ai.reranking import build_lexical_query
from app.ai.vectorstore import PgVectorStore
from app.models.document import Document, DocumentChunks
from app.models.note import Notes
from app.models.user import User


def _create_user(session: Session) -> User:
    user = User(
        email="retrieval@example.com",
        hashed_password="not-used-in-this-test",
        is_verified=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_lexical_query_recovers_compact_project_name() -> None:
    lexical_query = build_lexical_query("Explain the project go torrent")

    assert lexical_query.phrase == "go torrent"
    assert lexical_query.compact_phrase == "gotorrent"


def test_document_lexical_search_matches_spaced_name(session: Session) -> None:
    user = _create_user(session)
    assert user.id is not None
    document = Document(
        user_id=user.id,
        title="Karthik Das P CV",
        file_name="cv.md",
        file_path="/tmp/cv.md",
        file_size=200,
        file_type="markdown",
        mime_type="text/markdown",
        status="completed",
        content="GoTorrent is a BitTorrent client implemented in Go.",
    )
    session.add(document)
    session.commit()
    session.refresh(document)
    assert document.id is not None
    chunk = DocumentChunks(
        document_id=document.id,
        chunk_index=0,
        content="GoTorrent implements the BitTorrent wire protocol from scratch in Go.",
        vector_id="chunk-1",
    )
    session.add(chunk)
    session.commit()

    hits = PgVectorStore(session=session).lexical_chunk_search(
        user_id=user.id,
        query=build_lexical_query("Explain the project go torrent"),
        top_k=5,
    )

    assert len(hits) == 1
    assert hits[0].document_id == document.id
    assert hits[0].exact_match is True
    assert hits[0].lexical_score == 1.0


def test_note_lexical_search_matches_exact_title(session: Session) -> None:
    user = _create_user(session)
    assert user.id is not None
    note = Notes(
        user_id=user.id,
        title="AtlasCompiler",
        content="A compiler project with an SSA intermediate representation.",
    )
    session.add(note)
    session.commit()
    session.refresh(note)
    assert note.id is not None

    hits = PgVectorStore(session=session).lexical_note_search(
        user_id=user.id,
        query=build_lexical_query("Tell me about atlas compiler"),
        top_k=5,
    )

    assert len(hits) == 1
    assert hits[0].note_id == note.id
    assert hits[0].exact_match is True


def test_document_context_expands_and_merges_neighboring_chunks(session: Session) -> None:
    user = _create_user(session)
    assert user.id is not None
    document = Document(
        user_id=user.id,
        title="Karthik Das P CV",
        file_name="cv.md",
        file_path="/tmp/cv.md",
        file_size=500,
        file_type="markdown",
        mime_type="text/markdown",
        status="completed",
        content="GoTorrent project details",
    )
    session.add(document)
    session.commit()
    session.refresh(document)
    assert document.id is not None
    chunks = [
        DocumentChunks(
            document_id=document.id,
            chunk_index=3,
            content="Previous project tail.\n## GoTorrent\nTechnologies: Go",
            vector_id="chunk-3",
        ),
        DocumentChunks(
            document_id=document.id,
            chunk_index=4,
            content="Technologies: Go\n- BitTorrent wire protocol\n- HTTP tracker",
            vector_id="chunk-4",
        ),
        DocumentChunks(
            document_id=document.id,
            chunk_index=5,
            content="- HTTP tracker\n- Crash-safe resume\n# Skills",
            vector_id="chunk-5",
        ),
    ]
    session.add_all(chunks)
    session.commit()
    for chunk in chunks:
        session.refresh(chunk)
    assert chunks[1].id is not None
    source = RAGContextSource(
        citation_id=1,
        source_type="document",
        source_id=document.id,
        title=document.title,
        content=chunks[1].content,
        vector_score=None,
        hybrid_score=0.8,
        chunk_id=chunks[1].id,
        chunk_index=4,
        origin="hybrid",
    )

    expanded = _expand_document_context_sources(session=session, sources=[source])

    assert len(expanded) == 1
    assert expanded[0].chunk_index == 3
    assert expanded[0].chunk_end_index == 5
    assert "## GoTorrent" in expanded[0].content
    assert "Crash-safe resume" in expanded[0].content
    assert expanded[0].content.count("Technologies: Go") == 1
    assert expanded[0].content.count("- HTTP tracker") == 1


def _document(session: Session, user: User, title: str, language: str, chunks: list[str]) -> int:
    assert user.id is not None
    document = Document(
        user_id=user.id,
        title=title,
        file_name="doc.txt",
        file_path="/tmp/doc.txt",
        file_size=1,
        file_type="text",
        mime_type="text/plain",
        status="completed",
        language=language,
    )
    session.add(document)
    session.flush()
    assert document.id is not None
    for index, content in enumerate(chunks):
        session.add(
            DocumentChunks(
                document_id=document.id,
                chunk_index=index,
                content=content,
                vector_id=f"chunk-{document.id}-{index}",
            )
        )
    session.commit()
    return document.id


def test_a_document_is_stemmed_in_its_own_language(session: Session) -> None:
    user = _create_user(session)
    assert user.id is not None
    german = _document(session, user, "Notizen", "de", ["Die alten Häuser am Fluss"])
    # English stemming leaves "häuser" alone, so only German finds it from "Haus"
    _document(session, user, "Notes", "en", ["Die alten Häuser am Fluss"])

    hits = PgVectorStore(session=session).lexical_chunk_search(
        user_id=user.id, query=build_lexical_query("Haus"), top_k=5
    )

    assert [hit.document_id for hit in hits] == [german]
    assert hits[0].exact_match is False
    assert hits[0].lexical_score > 0


def test_a_document_title_match_finds_its_chunks(session: Session) -> None:
    user = _create_user(session)
    assert user.id is not None
    document_id = _document(session, user, "Quarterly budgets", "en", ["Unrelated text."])

    hits = PgVectorStore(session=session).lexical_chunk_search(
        user_id=user.id, query=build_lexical_query("budget"), top_k=5
    )

    assert [hit.document_id for hit in hits] == [document_id]


def test_query_words_split_between_title_and_text_still_match(session: Session) -> None:
    user = _create_user(session)
    assert user.id is not None
    document_id = _document(
        session, user, "Budget report", "en", ["Forecast improved this quarter.", "Other text."]
    )
    # Only the title or only the text: not every query word, so no match
    _document(session, user, "Budget notes", "en", ["Nothing relevant."])

    hits = PgVectorStore(session=session).lexical_chunk_search(
        user_id=user.id, query=build_lexical_query("budget forecast"), top_k=5
    )

    assert [(hit.document_id, hit.chunk_index) for hit in hits] == [(document_id, 0)]


def test_lexical_search_reads_the_stored_vector_indexes(session: Session) -> None:
    user = _create_user(session)
    assert user.id is not None
    document_id = _document(session, user, "Log", "en", ["the zebra migration"])
    # A workspace large enough that reading every row costs more than the index
    connection = session.connection()
    connection.execute(
        text(
            """
            INSERT INTO document_chunks
                (created_at, updated_at, document_id, chunk_index, content, vector_id)
            SELECT NOW(), NOW(), :document_id, n, repeat('routine entry number ' || n || ' ', 40),
                'v' || n
            FROM generate_series(1, 20000) AS n
            """
        ),
        {"document_id": document_id},
    )
    session.add(Notes(user_id=user.id, title="Sighting", content="the zebra migration"))
    session.flush()
    connection.execute(
        text(
            """
            INSERT INTO notes (
                created_at, updated_at, portable_id, user_id, title, content, content_type,
                keywords, ai_generated, is_favorite, is_archived, is_pinned, version, revision,
                is_public, is_locked, is_deleted, last_accessed_at, last_edited_at
            )
            SELECT NOW(), NOW(), gen_random_uuid(), :user_id, 'Note ' || n,
                repeat('routine entry number ' || n || ' ', 40), 'markdown', '{}', false, false,
                false, false,
                1, 1, false, false, false, NOW(), NOW()
            FROM generate_series(1, 20000) AS n
            """
        ),
        {"user_id": user.id},
    )
    connection.exec_driver_sql("ANALYZE document_chunks, documents, notes")

    plans: list[str] = []
    original_execute = connection.execute

    def explain(statement, parameters=None, **kwargs):  # noqa: ANN001, ANN202
        if "lexical_matches" in str(statement):
            plan = original_execute(text(f"EXPLAIN {statement}"), parameters, **kwargs)
            plans.append("\n".join(row[0] for row in plan))
        return original_execute(statement, parameters, **kwargs)

    connection.execute = explain  # pyright: ignore[reportAttributeAccessIssue]
    try:
        store = PgVectorStore(session=session)
        chunk_hits = store.lexical_chunk_search(
            user_id=user.id, query=build_lexical_query("zebras"), top_k=5
        )
        note_hits = store.lexical_note_search(
            user_id=user.id, query=build_lexical_query("zebras"), top_k=5
        )
    finally:
        del connection.execute

    assert [hit.content for hit in chunk_hits] == ["the zebra migration"]
    assert [hit.content for hit in note_hits] == ["the zebra migration"]
    chunk_plan, note_plan = plans
    assert "ix_document_chunks_search_vector" in chunk_plan
    assert "ix_notes_search_vector" in note_plan
    assert "to_tsvector" not in chunk_plan + note_plan  # read, never computed per row
