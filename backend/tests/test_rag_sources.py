from typing import cast
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from sqlmodel import Session

from app.ai.llm import build_chat_messages
from app.ai.rag import (
    RAGContextSource,
    WorkspaceInventoryEntry,
    _build_cited_sources_payload,
    _build_context_chunks,
    _build_sources_payload,
    _extract_citation_ids,
    _format_citation_context,
    _format_workspace_inventory,
    _infer_citation_ids,
    _insert_inferred_citations,
    _is_casual_conversation,
    _load_workspace_inventory,
    _merge_inventory_sources,
    _needs_history_for_retrieval,
    _needs_workspace_inventory,
    _repair_exact_terms,
    _resolve_retrieval_context,
    run_rag_pipeline,
)
from app.ai.vectorstore import (
    LexicalChunkSearchResult,
    NoteVectorSearchResult,
    VectorSearchResult,
)
from app.models.document import Document
from app.models.note import Notes


class RAGNoteSourceTests(TestCase):
    def setUp(self) -> None:
        self.note_hit = NoteVectorSearchResult(
            note_id=9,
            title="Launch Plan",
            content="The release window is Friday morning.",
            score=0.72,
        )

    def test_note_is_included_in_model_context(self) -> None:
        context = _build_context_chunks(
            chunk_hits=[],
            note_hits=[self.note_hit],
            document_map={},
        )

        self.assertEqual(len(context), 1)
        self.assertIn("[Note: Launch Plan", context[0])
        self.assertIn("Friday morning", context[0])

    def test_note_is_exposed_as_a_source(self) -> None:
        sources = _build_sources_payload(
            chunk_hits=[],
            note_hits=[self.note_hit],
            document_map={},
        )

        self.assertEqual(sources["documents"], [])
        self.assertEqual(sources["chunks"], [])
        self.assertEqual(sources["notes"][0]["note_id"], 9)
        self.assertEqual(sources["notes"][0]["title"], "Launch Plan")

    def test_context_is_internal_and_recent_history_is_preserved(self) -> None:
        messages = build_chat_messages(
            user_prompt="When is it?",
            context_chunks=["[Note: Launch Plan]\nFriday morning"],
            system_prompt="Answer briefly.",
            conversation_history=[{"role": "user", "content": "Tell me about launch."}],
        )

        self.assertEqual([message["role"] for message in messages], ["system", "user", "user"])
        self.assertNotIn("Friday morning", messages[0]["content"])
        self.assertIn("Friday morning", messages[-1]["content"])
        self.assertIn("CURRENT QUESTION:\nWhen is it?", messages[-1]["content"])

    def test_near_miss_exact_terms_are_repaired_from_context(self) -> None:
        answer = 'Use "SILVER LAANTNERN" after approval from Nilah Rao.'
        context = ["The launch phrase is SILVER LANTERN. Approval comes from Nila Rao."]

        repaired = _repair_exact_terms(answer, context)

        self.assertEqual(repaired, 'Use "SILVER LANTERN" after approval from Nila Rao.')

    def test_project_overview_question_requests_workspace_inventory(self) -> None:
        self.assertTrue(_needs_workspace_inventory("What are all the projects I have?"))
        self.assertTrue(_needs_workspace_inventory("Tell me about my projects\nWhat are they?"))
        self.assertFalse(_needs_workspace_inventory("When is the Atlas launch?"))

    def test_casual_conversation_bypasses_workspace_retrieval(self) -> None:
        self.assertTrue(_is_casual_conversation("What's up?"))
        self.assertTrue(_is_casual_conversation("How are you?"))
        self.assertTrue(_is_casual_conversation("What can you do?"))
        self.assertFalse(_is_casual_conversation("What are my projects?"))

    def test_casual_response_does_not_retrieve_workspace_content(self) -> None:
        with (
            patch("app.ai.rag.generate_embedding") as generate_embedding,
            patch("app.ai.rag.LLMService") as llm_service,
        ):
            llm_service.return_value.generate_response = AsyncMock(
                return_value="Doing well. What can I help with?"
            )

            result = run_rag_pipeline(
                session=cast(Session, object()),
                user_id=1,
                query="What's up?",
            )

        generate_embedding.assert_not_called()
        self.assertEqual(result.answer, "Doing well. What can I help with?")
        self.assertEqual(result.sources, {"documents": [], "chunks": [], "notes": []})

    def test_only_ambiguous_follow_ups_expand_the_retrieval_query(self) -> None:
        self.assertTrue(_needs_history_for_retrieval("When is it?"))
        self.assertTrue(_needs_history_for_retrieval("What about the deadline?"))
        self.assertFalse(_needs_history_for_retrieval("Explain the Atlas project"))

    def test_follow_up_recovers_subject_and_previous_document_source(self) -> None:
        history = [
            {"role": "user", "content": "What are my projects?"},
            {
                "role": "assistant",
                "content": "LMS TUI, Personal AI Knowledge Assistant, and GoTorrent [1].",
                "sources": {
                    "documents": [{"document_id": 22}],
                    "notes": [],
                    "chunks": [],
                },
            },
            {"role": "user", "content": "Explain the project go torrent"},
            {
                "role": "assistant",
                "content": "GoTorrent is a BitTorrent client [1].",
                "sources": {
                    "documents": [{"document_id": 22}],
                    "notes": [],
                    "chunks": [],
                },
            },
        ]

        context = _resolve_retrieval_context(
            query="Give more details about the project",
            conversation_history=history,
        )

        self.assertTrue(context.is_follow_up)
        self.assertIn("go torrent", context.retrieval_query.casefold())
        self.assertEqual(context.prior_document_ids, (22,))
        self.assertEqual(context.prior_note_ids, ())

    def test_new_topic_does_not_inherit_previous_sources(self) -> None:
        context = _resolve_retrieval_context(
            query="How far is the Moon?",
            conversation_history=[
                {"role": "user", "content": "Explain GoTorrent"},
                {
                    "role": "assistant",
                    "content": "GoTorrent is a BitTorrent client [1].",
                    "sources": {
                        "documents": [{"document_id": 22}],
                        "notes": [],
                        "chunks": [],
                    },
                },
            ],
        )

        self.assertFalse(context.is_follow_up)
        self.assertEqual(context.retrieval_query, "How far is the Moon?")
        self.assertEqual(context.prior_document_ids, ())

    def test_inventory_context_and_sources_include_every_entry(self) -> None:
        entries = [
            WorkspaceInventoryEntry("document", 1, "Atlas", "A launch planning project."),
            WorkspaceInventoryEntry("document", 2, "Beacon", "A reporting project."),
            WorkspaceInventoryEntry("note", 3, "Cedar", "A research project."),
        ]

        context = _format_workspace_inventory(entries)
        sources = {"documents": [], "chunks": [], "notes": []}
        _merge_inventory_sources(sources=sources, inventory_entries=entries)

        self.assertIn("Atlas", context)
        self.assertIn("Beacon", context)
        self.assertIn("Cedar", context)
        self.assertEqual(
            [document["title"] for document in sources["documents"]],
            ["Atlas", "Beacon"],
        )
        self.assertEqual(sources["notes"][0]["title"], "Cedar")

    def test_workspace_inventory_uses_complete_document_content(self) -> None:
        complete_content = (
            f"Profile\n{'Experienced software engineer. ' * 30}\n\nProjects\n"
            "1. LMS TUI (Learning Management System Terminal UI)\n"
            "2. Personal AI Knowledge Assistant\n"
            "3. Vision Tracker"
        )
        document = Document(
            id=7,
            user_id=1,
            title="Karthik Das P CV",
            file_name="Karthik_Das_P_CV.md",
            file_path="/tmp/Karthik_Das_P_CV.md",
            file_size=len(complete_content),
            file_type="markdown",
            mime_type="text/markdown",
            status="completed",
            content=complete_content,
            content_preview="Projects: LMS TUI and Personal AI Knowledg...",
        )

        class QueryResult:
            def __init__(self, values: list[object]) -> None:
                self.values = values

            def all(self) -> list[object]:
                return self.values

        class FakeSession:
            def __init__(self) -> None:
                self.results = iter(([document], []))

            def exec(self, _statement: object) -> QueryResult:
                return QueryResult(list(next(self.results)))

        entries = _load_workspace_inventory(
            session=cast(Session, FakeSession()),
            user_id=1,
        )

        self.assertEqual(entries[0].description, complete_content)
        self.assertIn("Personal AI Knowledge Assistant", entries[0].description)
        self.assertIn("3. Vision Tracker", entries[0].description)

    def test_workspace_inventory_uses_complete_note_content(self) -> None:
        complete_content = (
            f"Background\n{'Research notes. ' * 55}\n\nProjects\n"
            "1. Atlas Compiler\n"
            "2. Beacon Search\n"
            "3. Cedar Runtime"
        )
        note = Notes(
            id=8,
            user_id=1,
            title="Project Catalog",
            content=complete_content,
            content_preview="Background and project notes...",
            summary="This note describes software projects.",
        )

        class QueryResult:
            def __init__(self, values: list[object]) -> None:
                self.values = values

            def all(self) -> list[object]:
                return self.values

        class FakeSession:
            def __init__(self) -> None:
                self.results = iter(([], [note]))

            def exec(self, _statement: object) -> QueryResult:
                return QueryResult(list(next(self.results)))

        entries = _load_workspace_inventory(
            session=cast(Session, FakeSession()),
            user_id=1,
        )

        self.assertEqual(entries[0].description, complete_content)
        self.assertIn("3. Cedar Runtime", entries[0].description)

    def test_citation_context_assigns_visible_source_numbers(self) -> None:
        sources = [
            RAGContextSource(
                citation_id=1,
                source_type="note",
                source_id=9,
                title="Launch Plan",
                content="The release window is Friday morning.",
                vector_score=0.72,
                hybrid_score=0.68,
            )
        ]

        context = _format_citation_context(sources)

        self.assertEqual(len(context), 1)
        self.assertIn("[Source 1 | Note: Launch Plan]", context[0])
        self.assertIn("Friday morning", context[0])

    def test_citation_parser_keeps_valid_ids_in_first_appearance_order(self) -> None:
        citation_ids = _extract_citation_ids(
            "Beacon is second [2]. Atlas is first [1][2]. Unknown [99].",
            valid_ids={1, 2, 3},
        )

        self.assertEqual(citation_ids, [2, 1])

    def test_empty_retrieval_fetches_candidates_once_before_reranking(self) -> None:
        class FakeSession:
            def get(self, *_: object) -> object:
                return type(
                    "Settings",
                    (),
                    {"top_k_results": 5, "similarity_threshold": 0.7},
                )()

        with (
            patch("app.ai.rag.generate_embedding", new=AsyncMock(return_value=([0.1], "embed"))),
            patch("app.ai.rag.ensure_workspace_embeddings"),
            patch("app.ai.rag.PgVectorStore") as vector_store_type,
            patch("app.ai.rag.LLMService") as llm_service,
        ):
            vector_store = vector_store_type.return_value
            vector_store.similarity_search.return_value = []
            vector_store.note_similarity_search.return_value = []
            llm_service.return_value.generate_response = AsyncMock(
                return_value="I could not find that in your workspace."
            )

            run_rag_pipeline(
                session=cast(Session, FakeSession()),
                user_id=1,
                query="When is the Atlas deadline?",
            )

        vector_store.similarity_search.assert_called_once()
        vector_store.note_similarity_search.assert_called_once()
        self.assertEqual(
            vector_store.similarity_search.call_args.kwargs["similarity_threshold"],
            None,
        )

    def test_only_sources_cited_by_the_answer_are_persisted(self) -> None:
        sources = [
            RAGContextSource(
                citation_id=1,
                source_type="note",
                source_id=9,
                title="Launch Plan",
                content="The release window is Friday morning.",
                vector_score=0.82,
                hybrid_score=0.78,
            ),
            RAGContextSource(
                citation_id=2,
                source_type="note",
                source_id=10,
                title="Meal Plan",
                content="Dinner is at seven.",
                vector_score=0.74,
                hybrid_score=0.61,
            ),
        ]

        payload = _build_cited_sources_payload(sources=sources, cited_ids=[1])

        self.assertEqual([note["note_id"] for note in payload["notes"]], [9])
        self.assertEqual(payload["notes"][0]["citation_id"], 1)
        self.assertEqual(payload["notes"][0]["origin"], "vector")

    def test_inventory_source_has_no_fabricated_similarity_score(self) -> None:
        sources = [
            RAGContextSource(
                citation_id=3,
                source_type="note",
                source_id=11,
                title="Beacon",
                content="A reporting project.",
                vector_score=None,
                hybrid_score=None,
                origin="inventory",
            )
        ]

        payload = _build_cited_sources_payload(sources=sources, cited_ids=[3])

        self.assertEqual(payload["notes"][0]["score"], None)
        self.assertEqual(payload["notes"][0]["origin"], "inventory")

    def test_pipeline_exposes_only_the_source_ollama_cites(self) -> None:
        class FakeSession:
            def get(self, *_: object) -> object:
                return type(
                    "Settings",
                    (),
                    {"top_k_results": 5, "similarity_threshold": 0.7},
                )()

        relevant = NoteVectorSearchResult(
            note_id=9,
            title="Launch Plan",
            content="The Atlas release window is Friday morning.",
            score=0.82,
        )
        extra = NoteVectorSearchResult(
            note_id=10,
            title="Project Archive",
            content="Historical project notes.",
            score=0.74,
        )

        with (
            patch("app.ai.rag.generate_embedding", new=AsyncMock(return_value=([0.1], "embed"))),
            patch("app.ai.rag.ensure_workspace_embeddings"),
            patch("app.ai.rag.PgVectorStore") as vector_store_type,
            patch("app.ai.rag.LLMService") as llm_service,
        ):
            vector_store = vector_store_type.return_value
            vector_store.similarity_search.return_value = []
            vector_store.note_similarity_search.return_value = [relevant, extra]
            llm_service.return_value.generate_response = AsyncMock(
                return_value="The Atlas release window is Friday morning [1]."
            )

            result = run_rag_pipeline(
                session=cast(Session, FakeSession()),
                user_id=1,
                query="When is the Atlas release window?",
            )

        self.assertEqual([note["note_id"] for note in result.sources["notes"]], [9])
        self.assertEqual(result.sources["notes"][0]["citation_id"], 1)

    def test_pipeline_rescues_exact_name_below_semantic_threshold(self) -> None:
        class FakeSession:
            def get(self, *_: object) -> object:
                return type(
                    "Settings",
                    (),
                    {"top_k_results": 5, "similarity_threshold": 0.7},
                )()

        content = "GoTorrent implements the BitTorrent wire protocol from scratch in Go."
        vector_hit = VectorSearchResult(
            chunk_id=46,
            document_id=22,
            chunk_index=4,
            content=content,
            score=0.646,
        )
        lexical_hit = LexicalChunkSearchResult(
            chunk_id=46,
            document_id=22,
            chunk_index=4,
            content=content,
            lexical_score=1.0,
            exact_match=True,
        )
        document = Document(
            id=22,
            user_id=1,
            title="Karthik Das P CV",
            file_name="cv.md",
            file_path="/tmp/cv.md",
            file_size=len(content),
            file_type="markdown",
            mime_type="text/markdown",
            status="completed",
            content=content,
        )

        with (
            patch("app.ai.rag.generate_embedding", new=AsyncMock(return_value=([0.1], "embed"))),
            patch("app.ai.rag.ensure_workspace_embeddings"),
            patch("app.ai.rag._load_document_map", return_value={22: document}),
            patch(
                "app.ai.rag._expand_document_context_sources",
                side_effect=lambda **kwargs: list(kwargs["sources"]),
            ),
            patch("app.ai.rag.PgVectorStore") as vector_store_type,
            patch("app.ai.rag.LLMService") as llm_service,
        ):
            vector_store = vector_store_type.return_value
            vector_store.similarity_search.return_value = [vector_hit]
            vector_store.note_similarity_search.return_value = []
            vector_store.lexical_chunk_search.return_value = [lexical_hit]
            vector_store.lexical_note_search.return_value = []
            llm_service.return_value.generate_response = AsyncMock(
                return_value="GoTorrent is a BitTorrent client implemented in Go [1]."
            )

            result = run_rag_pipeline(
                session=cast(Session, FakeSession()),
                user_id=1,
                query="Explain the project go torrent",
            )

        self.assertEqual(result.sources["documents"][0]["document_id"], 22)
        self.assertEqual(result.sources["documents"][0]["origin"], "hybrid")
        self.assertIsNone(result.sources["documents"][0]["max_score"])
        self.assertEqual(
            vector_store.similarity_search.call_args.kwargs["similarity_threshold"],
            None,
        )
        self.assertGreaterEqual(vector_store.similarity_search.call_args.kwargs["top_k"], 20)

    def test_follow_up_searches_previous_document_before_global_workspace(self) -> None:
        class FakeSession:
            def get(self, *_: object) -> object:
                return type(
                    "Settings",
                    (),
                    {"top_k_results": 5, "similarity_threshold": 0.7},
                )()

        content = "GoTorrent implements the BitTorrent wire protocol from scratch in Go."
        lexical_hit = LexicalChunkSearchResult(
            chunk_id=46,
            document_id=22,
            chunk_index=4,
            content=content,
            lexical_score=1.0,
            exact_match=True,
        )
        document = Document(
            id=22,
            user_id=1,
            title="Karthik Das P CV",
            file_name="cv.md",
            file_path="/tmp/cv.md",
            file_size=len(content),
            file_type="markdown",
            mime_type="text/markdown",
            status="completed",
            content=content,
        )
        history = [
            {"role": "user", "content": "Explain the project go torrent"},
            {
                "role": "assistant",
                "content": "GoTorrent is a BitTorrent client [1].",
                "sources": {
                    "documents": [{"document_id": 22}],
                    "notes": [],
                    "chunks": [],
                },
            },
        ]

        with (
            patch("app.ai.rag.generate_embedding", new=AsyncMock(return_value=([0.1], "embed"))),
            patch("app.ai.rag.ensure_workspace_embeddings"),
            patch("app.ai.rag._load_document_map", return_value={22: document}),
            patch(
                "app.ai.rag._expand_document_context_sources",
                side_effect=lambda **kwargs: list(kwargs["sources"]),
            ),
            patch("app.ai.rag.PgVectorStore") as vector_store_type,
            patch("app.ai.rag.LLMService") as llm_service,
        ):
            vector_store = vector_store_type.return_value
            vector_store.similarity_search.return_value = []
            vector_store.note_similarity_search.return_value = []
            vector_store.lexical_chunk_search.return_value = [lexical_hit]
            vector_store.lexical_note_search.return_value = []
            llm_service.return_value.generate_response = AsyncMock(
                return_value="GoTorrent implements the BitTorrent wire protocol [1]."
            )

            result = run_rag_pipeline(
                session=cast(Session, FakeSession()),
                user_id=1,
                query="Give more details about the project",
                conversation_history=history,
            )

        self.assertEqual(result.sources["documents"][0]["document_id"], 22)
        self.assertEqual(
            vector_store.similarity_search.call_args.kwargs["document_ids"],
            (22,),
        )
        self.assertEqual(
            vector_store.lexical_chunk_search.call_args.kwargs["document_ids"],
            (22,),
        )
        vector_store.similarity_search.assert_called_once()

    def test_workspace_overview_fetches_candidates_before_thresholding(self) -> None:
        class FakeSession:
            def get(self, *_: object) -> object:
                return type(
                    "Settings",
                    (),
                    {"top_k_results": 5, "similarity_threshold": 0.7},
                )()

        with (
            patch("app.ai.rag.generate_embedding", new=AsyncMock(return_value=([0.1], "embed"))),
            patch("app.ai.rag.ensure_workspace_embeddings"),
            patch("app.ai.rag._load_workspace_inventory", return_value=[]),
            patch("app.ai.rag.PgVectorStore") as vector_store_type,
            patch("app.ai.rag.LLMService") as llm_service,
        ):
            vector_store = vector_store_type.return_value
            vector_store.similarity_search.return_value = []
            vector_store.note_similarity_search.return_value = []
            llm_service.return_value.generate_response = AsyncMock(
                return_value="No projects found."
            )

            run_rag_pipeline(
                session=cast(Session, FakeSession()),
                user_id=1,
                query="What are all my projects?",
            )

        self.assertEqual(
            vector_store.similarity_search.call_args.kwargs["similarity_threshold"],
            None,
        )

    def test_infers_source_when_small_model_omits_citation_marker(self) -> None:
        sources = [
            RAGContextSource(
                citation_id=1,
                source_type="note",
                source_id=9,
                title="Atlas Horizon",
                content="The Atlas Horizon launch window is Friday morning.",
                vector_score=0.82,
                hybrid_score=0.78,
            ),
            RAGContextSource(
                citation_id=2,
                source_type="note",
                source_id=10,
                title="Meal Plan",
                content="Dinner is at seven.",
                vector_score=0.74,
                hybrid_score=0.61,
            ),
        ]

        citation_ids = _infer_citation_ids(
            "Atlas Horizon launches on Friday morning.",
            sources=sources,
        )

        self.assertEqual(citation_ids, [1])

    def test_infers_each_named_source_in_workspace_overview(self) -> None:
        sources = [
            RAGContextSource(1, "note", 1, "Atlas Horizon", "Atlas project", None, None),
            RAGContextSource(2, "note", 2, "Beacon Ledger", "Beacon project", None, None),
            RAGContextSource(3, "note", 3, "Cedar Lens", "Cedar project", None, None),
        ]
        answer = "Projects: Atlas Horizon, Beacon Ledger, and Cedar Lens."

        citation_ids = _infer_citation_ids(answer, sources=sources)
        enriched = _insert_inferred_citations(answer, sources=sources, cited_ids=citation_ids)

        self.assertEqual(citation_ids, [1, 2, 3])
        self.assertIn("Atlas Horizon [1]", enriched)
        self.assertIn("Beacon Ledger [2]", enriched)
        self.assertIn("Cedar Lens [3]", enriched)

    def test_general_answer_does_not_infer_workspace_sources(self) -> None:
        sources = [
            RAGContextSource(
                1,
                "note",
                1,
                "Atlas Horizon",
                "The launch window is Friday morning.",
                0.8,
                0.75,
            )
        ]

        citation_ids = _infer_citation_ids(
            "The Moon is Earth's natural satellite.",
            sources=sources,
        )

        self.assertEqual(citation_ids, [])
