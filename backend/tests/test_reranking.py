from app.ai.reranking import RerankCandidate, rerank_candidates


def _candidate(
    key: str,
    *,
    title: str,
    content: str,
    score: float,
    lexical_score: float = 0.0,
    exact_match: bool = False,
    prior_source: bool = False,
) -> RerankCandidate:
    return RerankCandidate(
        source_key=key,
        source_type="note",
        source_id=int(key.removeprefix("note:")),
        title=title,
        content=content,
        vector_score=score,
        lexical_score=lexical_score,
        exact_match=exact_match,
        prior_source=prior_source,
    )


def test_exact_name_match_can_rescue_candidate_below_vector_threshold() -> None:
    candidates = [
        _candidate(
            "note:1",
            title="Karthik Das P CV",
            content="GoTorrent implements the BitTorrent wire protocol in Go.",
            score=0.646,
            lexical_score=1.0,
            exact_match=True,
        )
    ]

    ranked = rerank_candidates(
        query="Explain the project go torrent",
        candidates=candidates,
        similarity_threshold=0.70,
        limit=5,
    )

    assert [item.source_key for item in ranked] == ["note:1"]
    assert ranked[0].match_type == "hybrid"


def test_weak_candidate_below_threshold_without_lexical_support_is_rejected() -> None:
    candidates = [
        _candidate(
            "note:1",
            title="Meeting archive",
            content="Routine planning notes.",
            score=0.69,
        )
    ]

    ranked = rerank_candidates(
        query="Explain the project go torrent",
        candidates=candidates,
        similarity_threshold=0.70,
        limit=5,
    )

    assert ranked == []


def test_prior_source_breaks_tie_without_overriding_relevance() -> None:
    candidates = [
        _candidate(
            "note:1",
            title="GoTorrent",
            content="BitTorrent client in Go.",
            score=0.72,
            lexical_score=1.0,
            exact_match=True,
            prior_source=True,
        ),
        _candidate(
            "note:2",
            title="GoTorrent copy",
            content="BitTorrent client in Go.",
            score=0.72,
            lexical_score=1.0,
            exact_match=True,
        ),
    ]

    ranked = rerank_candidates(
        query="Tell me more about GoTorrent",
        candidates=candidates,
        similarity_threshold=0.70,
        limit=5,
    )

    assert [item.source_key for item in ranked] == ["note:1", "note:2"]
    assert ranked[0].hybrid_score > ranked[1].hybrid_score


def test_lexical_support_removes_semantically_close_but_unrelated_results() -> None:
    candidates = [
        _candidate(
            "note:1",
            title="Weekly notes",
            content="A general planning update without the requested project name.",
            score=0.78,
        ),
        _candidate(
            "note:2",
            title="Atlas launch plan",
            content="The launch deadline is Friday morning.",
            score=0.76,
        ),
        _candidate(
            "note:3",
            title="Atlas archive",
            content="An unrelated historical record.",
            score=0.71,
        ),
    ]

    ranked = rerank_candidates(
        query="Atlas launch deadline",
        candidates=candidates,
        similarity_threshold=0.70,
        limit=3,
        hybrid_score_window=0.25,
    )

    assert [item.source_key for item in ranked] == ["note:2"]


def test_relative_hybrid_window_removes_weak_tail_results() -> None:
    candidates = [
        _candidate(
            "note:1",
            title="Atlas launch",
            content="The Atlas launch deadline is Friday.",
            score=0.91,
        ),
        _candidate(
            "note:2",
            title="Atlas launch checklist",
            content="Launch preparation for Atlas.",
            score=0.86,
        ),
        _candidate(
            "note:3",
            title="Meeting archive",
            content="General meetings and status updates.",
            score=0.70,
        ),
    ]

    ranked = rerank_candidates(
        query="Atlas launch deadline",
        candidates=candidates,
        similarity_threshold=0.70,
        limit=5,
        hybrid_score_window=0.15,
    )

    assert [item.source_key for item in ranked] == ["note:1", "note:2"]


def test_equal_candidates_use_stable_source_key_tie_breaking() -> None:
    candidates = [
        _candidate("note:2", title="Atlas", content="Atlas launch", score=0.8),
        _candidate("note:1", title="Atlas", content="Atlas launch", score=0.8),
    ]

    ranked = rerank_candidates(
        query="Atlas launch",
        candidates=candidates,
        similarity_threshold=0.70,
        limit=5,
    )

    assert [item.source_key for item in ranked] == ["note:1", "note:2"]


def test_plural_query_terms_match_singular_source_terms() -> None:
    candidates = [
        _candidate(
            "note:1",
            title="Atlas project",
            content="A release automation project.",
            score=0.76,
        ),
        _candidate(
            "note:2",
            title="Shopping list",
            content="Groceries for the week.",
            score=0.78,
        ),
    ]

    ranked = rerank_candidates(
        query="List all my projects",
        candidates=candidates,
        similarity_threshold=0.7,
        limit=2,
    )

    assert ranked[0].source_key == "note:1"
