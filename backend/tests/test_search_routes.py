from unittest import TestCase

from fastapi.routing import APIRoute

from app.ai.vectorstore import ChatVectorSearchResult, PgVectorStore
from app.api.routes.search import (
    SEMANTIC_SIMILARITY_THRESHOLD,
    _chat_results_from_hits,
    _is_relevant_semantic_score,
    _keep_best,
    _merge_result,
    router,
)
from app.schemas.search import SearchResultItem


class SearchRouteTests(TestCase):
    def test_search_uses_non_redirecting_canonical_path(self) -> None:
        route_paths = {route.path for route in router.routes if isinstance(route, APIRoute)}

        self.assertIn("/search", route_paths)

    def test_semantic_results_merge_without_hiding_other_entity_types(self) -> None:
        results: dict[tuple[str, int], SearchResultItem] = {}
        _merge_result(
            results,
            SearchResultItem(
                id=4,
                entity_type="chat",
                title="Conversation",
                snippet="Exact repeated query",
                score=0.08,
            ),
        )
        _merge_result(
            results,
            SearchResultItem(
                id=4,
                entity_type="note",
                title="Research plan",
                snippet="Contextually related content",
                score=0.72,
            ),
        )

        self.assertEqual(set(results), {("chat", 4), ("note", 4)})

    def test_stronger_semantic_match_replaces_lexical_preview(self) -> None:
        results: dict[tuple[str, int], SearchResultItem] = {}
        _merge_result(
            results,
            SearchResultItem(
                id=9,
                entity_type="document",
                snippet="Weak lexical preview",
                score=0.05,
            ),
        )
        _merge_result(
            results,
            SearchResultItem(
                id=9,
                entity_type="document",
                snippet="Relevant semantic passage",
                score=0.81,
            ),
        )

        self.assertEqual(results[("document", 9)].snippet, "Relevant semantic passage")
        self.assertEqual(results[("document", 9)].score, 0.81)

    def test_semantic_threshold_rejects_unrelated_results(self) -> None:
        self.assertTrue(_is_relevant_semantic_score(SEMANTIC_SIMILARITY_THRESHOLD))
        self.assertFalse(_is_relevant_semantic_score(SEMANTIC_SIMILARITY_THRESHOLD - 0.001))

    def test_chat_hits_collapse_to_best_message_per_session(self) -> None:
        hits = [
            ChatVectorSearchResult(
                message_id=11,
                session_id=4,
                session_title="Project planning",
                role="user",
                content="What projects are active?",
                score=0.63,
                created_at=None,
                updated_at=None,
            ),
            ChatVectorSearchResult(
                message_id=12,
                session_id=4,
                session_title="Project planning",
                role="assistant",
                content="The Orion Habitat Study is active.",
                score=0.82,
                created_at=None,
                updated_at=None,
            ),
            ChatVectorSearchResult(
                message_id=20,
                session_id=8,
                session_title="Unrelated",
                role="assistant",
                content="A weak match",
                score=SEMANTIC_SIMILARITY_THRESHOLD - 0.01,
                created_at=None,
                updated_at=None,
            ),
        ]

        results = _chat_results_from_hits(hits)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, 4)
        self.assertEqual(results[0].snippet, "The Orion Habitat Study is active.")
        self.assertEqual(results[0].score, 0.82)

    def test_exact_text_match_outranks_a_weaker_semantic_match(self) -> None:
        best: dict[int, tuple[float, str]] = {}

        _keep_best(best, 3, 0.66, "semantically close passage")
        _keep_best(best, 3, 1.0, "passage containing the exact phrase")
        _keep_best(best, 3, 0.4, "weak full-text match")

        self.assertEqual(best[3], (1.0, "passage containing the exact phrase"))

    def test_vector_store_exposes_chat_embedding_contract(self) -> None:
        self.assertTrue(hasattr(PgVectorStore, "chat_embedding_hashes"))
        self.assertTrue(hasattr(PgVectorStore, "store_chat_message_embeddings"))
        self.assertTrue(hasattr(PgVectorStore, "chat_similarity_search"))
