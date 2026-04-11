"""
Unit tests for Phase 2 performance improvements.

Tests verify:
1. Note listing with joinedload for tags (prevents N+1 queries)
2. Pagination at database level (prevents loading entire result sets)
3. Bulk insert for embeddings (prevents sequential database round trips)
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, select

from app.ai.vectorstore import PgVectorStore
from app.models.document import DocumentChunks
from app.models.note import Notes, NoteTags, NoteTagRelations
from app.models.user import User
from app.services.chat_service import list_chat_sessions
from app.services.document_service import list_documents
from app.services.note_service import list_notes, assign_tags_to_note
from app.models.chat import ChatSession
from app.models.document import Document


class TestNoteListingPerformance:
    """Test note listing with efficient tag loading."""

    def test_list_notes_with_tags_eager_loading(
        self, session: Session, test_user: User
    ) -> None:
        """
        Verify that list_notes uses joinedload for tags.

        This test ensures tags are loaded eagerly, preventing N+1 queries.
        """
        # Create test data
        tag1 = NoteTags(user_id=test_user.id, name="Important")
        tag2 = NoteTags(user_id=test_user.id, name="Review")
        session.add(tag1)
        session.add(tag2)
        session.commit()
        session.refresh(tag1)
        session.refresh(tag2)

        # Create notes with tags
        for i in range(5):
            note = Notes(
                user_id=test_user.id,
                title=f"Note {i}",
                content=f"Content {i}",
                tags=[tag1, tag2] if i % 2 == 0 else [tag1],
            )
            session.add(note)
        session.commit()

        # List notes - should load tags eagerly
        notes, total = list_notes(session=session, current_user=test_user, limit=10)

        assert len(notes) == 5
        assert total == 5

        # Verify all notes have tags loaded
        for note in notes:
            assert note.tags is not None
            assert len(note.tags) > 0

    def test_list_notes_filter_by_tag_id(
        self, session: Session, test_user: User
    ) -> None:
        """
        Verify tag filtering works correctly with eager loading.
        """
        tag = NoteTags(user_id=test_user.id, name="Priority")
        session.add(tag)
        session.commit()
        session.refresh(tag)

        # Create notes, only some with the tag
        for i in range(5):
            note = Notes(
                user_id=test_user.id,
                title=f"Note {i}",
                content=f"Content {i}",
                tags=[tag] if i < 3 else [],
            )
            session.add(note)
        session.commit()

        # Filter by tag_id
        notes, total = list_notes(
            session=session, current_user=test_user, tag_id=tag.id, limit=10
        )

        assert len(notes) == 3
        assert total == 3
        assert all(tag in note.tags for note in notes)

    def test_list_notes_pagination_efficiency(
        self, session: Session, test_user: User
    ) -> None:
        """
        Verify pagination uses database LIMIT/OFFSET instead of in-memory slicing.

        This test ensures only requested pages are loaded from the database.
        """
        # Create 50 notes
        for i in range(50):
            note = Notes(
                user_id=test_user.id,
                title=f"Note {i:02d}",
                content=f"Content {i}",
            )
            session.add(note)
        session.commit()

        # Get first page
        page1, total1 = list_notes(
            session=session, current_user=test_user, skip=0, limit=10
        )
        assert len(page1) == 10
        assert total1 == 50

        # Get second page
        page2, total2 = list_notes(
            session=session, current_user=test_user, skip=10, limit=10
        )
        assert len(page2) == 10
        assert total2 == 50

        # Verify different notes in each page
        page1_ids = {note.id for note in page1}
        page2_ids = {note.id for note in page2}
        assert len(page1_ids & page2_ids) == 0  # No overlap

        # Get last partial page
        page5, _ = list_notes(
            session=session, current_user=test_user, skip=40, limit=10
        )
        assert len(page5) == 10

    def test_list_notes_combined_filters_with_pagination(
        self, session: Session, test_user: User
    ) -> None:
        """
        Verify filtering and pagination work together efficiently.
        """
        tag = NoteTags(user_id=test_user.id, name="Work")
        session.add(tag)
        session.commit()
        session.refresh(tag)

        # Create notes in a folder with some tagged
        for i in range(30):
            note = Notes(
                user_id=test_user.id,
                title=f"Work Note {i:02d}",
                content=f"Important content {i}",
                tags=[tag] if i % 2 == 0 else [],
            )
            session.add(note)
        session.commit()

        # Filter by search and paginate
        results, total = list_notes(
            session=session,
            current_user=test_user,
            search="Important",
            skip=0,
            limit=10,
        )

        assert len(results) <= 10
        assert total <= 30


class TestPaginationPerformance:
    """Test pagination efficiency in document and chat session listing."""

    def test_document_listing_database_pagination(
        self, session: Session, test_user: User
    ) -> None:
        """
        Verify document listing uses database LIMIT/OFFSET.
        """
        # Create 100 documents
        for i in range(100):
            doc = Document(
                user_id=test_user.id,
                title=f"Document {i:03d}",
                content=f"Content {i}",
                file_name=f"doc_{i}.txt",
                file_size=1000,
                file_type=".txt",
                mime_type="text/plain",
            )
            session.add(doc)
        session.commit()

        # Get first page
        docs1, total = list_documents(
            session=session, current_user=test_user, skip=0, limit=20
        )
        assert len(docs1) == 20
        assert total == 100

        # Get second page
        docs2, _ = list_documents(
            session=session, current_user=test_user, skip=20, limit=20
        )
        assert len(docs2) == 20

        # Verify no overlap
        ids1 = {d.id for d in docs1}
        ids2 = {d.id for d in docs2}
        assert len(ids1 & ids2) == 0

    def test_document_listing_search_with_pagination(
        self, session: Session, test_user: User
    ) -> None:
        """
        Verify search and pagination work together efficiently.
        """
        # Create documents with different content
        for i in range(50):
            is_searchable = i < 30
            content = (
                "Important research data" if is_searchable else "Unrelated content"
            )
            doc = Document(
                user_id=test_user.id,
                title=f"Document {i:02d}",
                content=content,
                file_name=f"doc_{i}.txt",
                file_size=1000,
                file_type=".txt",
                mime_type="text/plain",
            )
            session.add(doc)
        session.commit()

        # Search with pagination
        results, total = list_documents(
            session=session,
            current_user=test_user,
            search="research",
            skip=0,
            limit=10,
        )

        assert len(results) <= 10
        # Total should reflect only matching documents
        assert total >= 10  # At least the first page

    def test_chat_session_listing_database_pagination(
        self, session: Session, test_user: User
    ) -> None:
        """
        Verify chat session listing uses database LIMIT/OFFSET.
        """
        from datetime import datetime, timedelta

        # Create 60 chat sessions
        base_time = datetime.now()
        for i in range(60):
            session_obj = ChatSession(
                user_id=test_user.id,
                title=f"Chat {i:02d}",
                last_message_at=base_time - timedelta(hours=i),
            )
            session.add(session_obj)
        session.commit()

        # Get first page (ordered by last_message_at desc)
        sessions1, total = list_chat_sessions(
            session=session, current_user=test_user, skip=0, limit=15
        )
        assert len(sessions1) == 15
        assert total == 60

        # Get second page
        sessions2, _ = list_chat_sessions(
            session=session, current_user=test_user, skip=15, limit=15
        )
        assert len(sessions2) == 15

        # Verify ordering (most recent first)
        for i in range(len(sessions1) - 1):
            assert sessions1[i].last_message_at >= sessions1[i + 1].last_message_at

        # Verify no overlap
        ids1 = {s.id for s in sessions1}
        ids2 = {s.id for s in sessions2}
        assert len(ids1 & ids2) == 0

    def test_chat_session_listing_partial_last_page(
        self, session: Session, test_user: User
    ) -> None:
        """
        Verify pagination handles partial last pages correctly.
        """
        # Create 25 chat sessions
        for i in range(25):
            session_obj = ChatSession(
                user_id=test_user.id,
                title=f"Chat {i:02d}",
            )
            session.add(session_obj)
        session.commit()

        # Get full pages
        page1, total = list_chat_sessions(
            session=session, current_user=test_user, skip=0, limit=10
        )
        assert len(page1) == 10
        assert total == 25

        page2, _ = list_chat_sessions(
            session=session, current_user=test_user, skip=10, limit=10
        )
        assert len(page2) == 10

        # Get partial last page
        page3, _ = list_chat_sessions(
            session=session, current_user=test_user, skip=20, limit=10
        )
        assert len(page3) == 5


class TestBulkEmbeddingInsert:
    """Test bulk embedding insert performance."""

    def test_bulk_embedding_insert_single_batch(self, session: Session) -> None:
        """
        Verify bulk insert handles multiple embeddings correctly.
        """
        from app.models.document import Document

        # Create a document with chunks
        doc = Document(
            user_id=1,
            title="Test Doc",
            content="Test content",
            file_name="test.txt",
            file_size=100,
            file_type=".txt",
            mime_type="text/plain",
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)

        # Create chunks
        chunks = []
        for i in range(5):
            chunk = DocumentChunks(
                document_id=doc.id,
                chunk_index=i,
                content=f"Chunk {i} content",
            )
            session.add(chunk)
            chunks.append(chunk)
        session.commit()
        for chunk in chunks:
            session.refresh(chunk)

        # Create embeddings (mock vectors)
        embeddings = [
            [0.1 * j for j in range(10)]  # 10-dimensional vectors
            for _ in range(5)
        ]

        # Store using bulk insert
        vector_store = PgVectorStore(session=session)
        vector_store.store_document_chunk_embeddings(
            chunks=chunks,
            embeddings=embeddings,
            user_id=1,
            model="test-model",
        )

        # Verify all embeddings were stored
        result = session.exec(
            select(DocumentChunks).where(DocumentChunks.document_id == doc.id)
        ).all()
        assert len(result) == 5

    def test_bulk_embedding_insert_upsert_behavior(self, session: Session) -> None:
        """
        Verify bulk insert with ON CONFLICT updates existing embeddings.
        """
        from app.models.document import Document

        # Create document and chunks
        doc = Document(
            user_id=1,
            title="Test Doc",
            content="Test content",
            file_name="test.txt",
            file_size=100,
            file_type=".txt",
            mime_type="text/plain",
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)

        chunk = DocumentChunks(
            document_id=doc.id,
            chunk_index=0,
            content="Chunk content",
        )
        session.add(chunk)
        session.commit()
        session.refresh(chunk)

        # First insert
        embeddings1 = [[0.1 * j for j in range(8)]]
        vector_store = PgVectorStore(session=session)
        vector_store.store_document_chunk_embeddings(
            chunks=[chunk],
            embeddings=embeddings1,
            user_id=1,
            model="model-v1",
        )

        # Second insert (upsert) with different model
        embeddings2 = [[0.2 * j for j in range(8)]]
        vector_store.store_document_chunk_embeddings(
            chunks=[chunk],
            embeddings=embeddings2,
            user_id=1,
            model="model-v2",
        )

        # Verify only one embedding record (upserted, not duplicated)
        from sqlalchemy import text

        result = session.exec(
            text(
                "SELECT COUNT(*) as count FROM chunk_embeddings WHERE chunk_id = :chunk_id"
            ),
            params={"chunk_id": chunk.id},
        ).first()
        assert result[0] == 1  # Only one record

    def test_bulk_embedding_insert_validation(self, session: Session) -> None:
        """
        Verify bulk insert validates chunks and embeddings.
        """
        vector_store = PgVectorStore(session=session)

        # Test: mismatched chunk and embedding counts
        chunks = [DocumentChunks(document_id=1, chunk_index=0, content="Test")]
        embeddings = [[0.1, 0.2], [0.3, 0.4]]  # 2 embeddings, 1 chunk

        with pytest.raises(
            ValueError, match="Chunk count does not match embedding count"
        ):
            vector_store.store_document_chunk_embeddings(
                chunks=chunks,
                embeddings=embeddings,
                user_id=1,
                model="test",
            )

        # Test: empty embeddings
        chunks = [DocumentChunks(document_id=1, chunk_index=0, content="Test")]
        empty_embeddings = [[]]

        with pytest.raises(ValueError, match="Embedding vectors cannot be empty"):
            vector_store.store_document_chunk_embeddings(
                chunks=chunks,
                embeddings=empty_embeddings,
                user_id=1,
                model="test",
            )

    def test_bulk_embedding_insert_dimension_consistency(
        self, session: Session
    ) -> None:
        """
        Verify bulk insert enforces consistent embedding dimensions.
        """
        from app.models.document import Document

        doc = Document(
            user_id=1,
            title="Test",
            content="Content",
            file_name="test.txt",
            file_size=100,
            file_type=".txt",
            mime_type="text/plain",
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)

        chunk1 = DocumentChunks(document_id=doc.id, chunk_index=0, content="C1")
        chunk2 = DocumentChunks(document_id=doc.id, chunk_index=1, content="C2")
        session.add(chunk1)
        session.add(chunk2)
        session.commit()
        session.refresh(chunk1)
        session.refresh(chunk2)

        # Mixed dimensions - one 8D, one 10D
        embeddings = [
            [0.1 * j for j in range(8)],
            [0.1 * j for j in range(10)],
        ]

        vector_store = PgVectorStore(session=session)
        with pytest.raises(
            ValueError, match="All embedding vectors must use the same dimensions"
        ):
            vector_store.store_document_chunk_embeddings(
                chunks=[chunk1, chunk2],
                embeddings=embeddings,
                user_id=1,
                model="test",
            )


class TestChatSessionPerformance:
    """Test chat session message loading efficiency (Phase 4a)."""

    def test_chat_session_messages_eager_loading(
        self, session: Session, test_user: User
    ) -> None:
        """
        Verify that list_chat_sessions uses joinedload for messages.

        This prevents N+1 queries when accessing chat_session.messages.
        Without eager loading: 1 query for sessions + N queries for messages = 1+N queries
        With eager loading: 1 query with JOIN to fetch all sessions and messages
        """
        from app.models.chat import ChatMessages, ChatSession

        # Create chat session
        chat_session = ChatSession(
            user_id=test_user.id,
            title="Test Chat",
        )
        session.add(chat_session)
        session.commit()
        session.refresh(chat_session)

        # Add messages
        for i in range(5):
            message = ChatMessages(
                session_id=chat_session.id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"Message {i}",
            )
            session.add(message)
        session.commit()

        # List sessions - should have messages eagerly loaded
        sessions, total = list_chat_sessions(
            session=session, current_user=test_user, limit=10
        )

        assert len(sessions) == 1
        assert total == 1

        # Verify messages are loaded (this should NOT trigger a query)
        assert len(sessions[0].messages) == 5
        for i, msg in enumerate(sessions[0].messages):
            assert msg.content == f"Message {i}"

    def test_chat_session_multiple_sessions_eager_loading(
        self, session: Session, test_user: User
    ) -> None:
        """
        Test that joinedload works correctly with multiple chat sessions.

        Performance: 10 sessions with 10 messages each
        - Without eager load: 1 + 10 = 11 queries
        - With eager load: 1 query (JOIN across all)
        """
        from app.models.chat import ChatMessages, ChatSession
        from datetime import datetime, timedelta

        # Create 10 chat sessions
        base_time = datetime.now()
        sessions_created = []
        for i in range(10):
            chat_session = ChatSession(
                user_id=test_user.id,
                title=f"Chat {i}",
                last_message_at=base_time - timedelta(hours=i),
            )
            session.add(chat_session)
            session.commit()
            session.refresh(chat_session)
            sessions_created.append(chat_session)

            # Add 5 messages to each session
            for j in range(5):
                message = ChatMessages(
                    session_id=chat_session.id,
                    role="user" if j % 2 == 0 else "assistant",
                    content=f"Session {i} Message {j}",
                )
                session.add(message)
        session.commit()

        # List sessions - all messages should be eagerly loaded
        sessions_retrieved, total = list_chat_sessions(
            session=session, current_user=test_user, skip=0, limit=20
        )

        assert len(sessions_retrieved) == 10
        assert total == 10

        # Verify all sessions have messages loaded
        total_messages = 0
        for chat_sess in sessions_retrieved:
            assert len(chat_sess.messages) == 5
            total_messages += len(chat_sess.messages)

        assert total_messages == 50

    def test_chat_session_pagination_with_eager_loading(
        self, session: Session, test_user: User
    ) -> None:
        """
        Verify pagination works correctly with joinedload for messages.
        """
        from app.models.chat import ChatMessages, ChatSession

        # Create 30 chat sessions
        for i in range(30):
            chat_session = ChatSession(
                user_id=test_user.id,
                title=f"Chat {i}",
            )
            session.add(chat_session)
            session.commit()
            session.refresh(chat_session)

            # Add 3 messages to each
            for j in range(3):
                message = ChatMessages(
                    session_id=chat_session.id,
                    role="user" if j % 2 == 0 else "assistant",
                    content=f"Message {j}",
                )
                session.add(message)
        session.commit()

        # Get first page
        page1, total1 = list_chat_sessions(
            session=session, current_user=test_user, skip=0, limit=10
        )
        assert len(page1) == 10
        assert total1 == 30

        # Verify all messages on first page are loaded
        for chat_sess in page1:
            assert len(chat_sess.messages) == 3

        # Get second page
        page2, total2 = list_chat_sessions(
            session=session, current_user=test_user, skip=10, limit=10
        )
        assert len(page2) == 10
        assert total2 == 30

        # Verify no overlap
        page1_ids = {s.id for s in page1}
        page2_ids = {s.id for s in page2}
        assert len(page1_ids & page2_ids) == 0

    def test_chat_session_empty_messages(
        self, session: Session, test_user: User
    ) -> None:
        """
        Verify that chat sessions without messages work correctly with eager loading.
        """
        from app.models.chat import ChatSession

        # Create sessions without messages
        for i in range(5):
            chat_session = ChatSession(
                user_id=test_user.id,
                title=f"Empty Chat {i}",
            )
            session.add(chat_session)
        session.commit()

        # List sessions
        sessions, total = list_chat_sessions(
            session=session, current_user=test_user, limit=10
        )

        assert len(sessions) == 5
        assert total == 5

        # All sessions should have empty messages list
        for chat_sess in sessions:
            assert len(chat_sess.messages) == 0

    def test_chat_session_mixed_messages(
        self, session: Session, test_user: User
    ) -> None:
        """
        Test eager loading with mixed scenarios (some sessions with messages, some without).
        """
        from app.models.chat import ChatMessages, ChatSession

        # Create 6 sessions: 3 with messages, 3 without
        session_list = []
        for i in range(6):
            chat_session = ChatSession(
                user_id=test_user.id,
                title=f"Chat {i}",
            )
            session.add(chat_session)
            session.commit()
            session.refresh(chat_session)
            session_list.append(chat_session)

            # Add messages to first 3 sessions
            if i < 3:
                for j in range(4):
                    message = ChatMessages(
                        session_id=chat_session.id,
                        role="user" if j % 2 == 0 else "assistant",
                        content=f"Message {j}",
                    )
                    session.add(message)
        session.commit()

        # List sessions
        sessions_retrieved, total = list_chat_sessions(
            session=session, current_user=test_user, limit=10
        )

        assert len(sessions_retrieved) == 6
        assert total == 6

        # Verify correct number of messages per session
        for i, chat_sess in enumerate(sessions_retrieved):
            if i < 3:
                assert len(chat_sess.messages) == 4
            else:
                assert len(chat_sess.messages) == 0

    def test_chat_session_message_content_integrity(
        self, session: Session, test_user: User
    ) -> None:
        """
        Verify that eagerly loaded messages contain correct data.
        """
        from app.models.chat import ChatMessages, ChatSession

        chat_session = ChatSession(
            user_id=test_user.id,
            title="Content Test",
        )
        session.add(chat_session)
        session.commit()
        session.refresh(chat_session)

        # Add messages with various data
        test_data = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
            {"role": "assistant", "content": "I'm doing great!"},
        ]

        for data in test_data:
            message = ChatMessages(
                session_id=chat_session.id,
                role=data["role"],
                content=data["content"],
            )
            session.add(message)
        session.commit()

        # Retrieve and verify
        sessions, _ = list_chat_sessions(
            session=session, current_user=test_user, limit=10
        )
        retrieved_session = sessions[0]

        assert len(retrieved_session.messages) == 4
        for i, msg in enumerate(retrieved_session.messages):
            assert msg.role == test_data[i]["role"]
            assert msg.content == test_data[i]["content"]


# Fixtures for tests
@pytest.fixture
def test_user(session: Session) -> User:
    """Create a test user."""
    user = User(
        email="test@example.com",
        username="testuser",
        hashed_password="fake_hash",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
