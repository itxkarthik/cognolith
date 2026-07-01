from unittest import TestCase

from fastapi.routing import APIRoute

from app.api.routes.search import _merge_result, router
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
