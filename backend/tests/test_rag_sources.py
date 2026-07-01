from typing import cast
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from sqlmodel import Session

from app.ai.llm import build_chat_messages
from app.ai.rag import (
    WorkspaceInventoryEntry,
    _build_context_chunks,
    _build_sources_payload,
    _format_workspace_inventory,
    _is_casual_conversation,
    _merge_inventory_sources,
    _needs_history_for_retrieval,
    _needs_workspace_inventory,
    _repair_exact_terms,
    run_rag_pipeline,
)
from app.ai.vectorstore import NoteVectorSearchResult


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
