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
