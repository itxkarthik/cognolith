from app.ai.grounding import validate_grounded_answer


def test_grounded_answer_accepts_known_citations() -> None:
    result = validate_grounded_answer("GoTorrent is a Go client [1].", valid_citation_ids={1})

    assert result.is_valid
    assert result.reason is None


def test_grounded_answer_rejects_unknown_citations() -> None:
    result = validate_grounded_answer("GoTorrent is a Go client [4].", valid_citation_ids={1})

    assert not result.is_valid
    assert result.reason == "unknown_citations"


def test_grounded_answer_rejects_missing_citations() -> None:
    result = validate_grounded_answer("GoTorrent is a Go client.", valid_citation_ids={1})

    assert not result.is_valid
    assert result.reason == "missing_citations"


def test_ungrounded_answer_never_requires_repair() -> None:
    result = validate_grounded_answer("Hello!", valid_citation_ids=set())

    assert result.is_valid
