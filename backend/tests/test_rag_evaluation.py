from pathlib import Path

import pytest

from app.ai.evaluation import (
    EvaluationCase,
    average_metric,
    evaluate_case,
    load_evaluation_cases,
)
from app.ai.reranking import RerankCandidate


def test_evaluation_metrics_measure_retrieval_and_reference_grounding() -> None:
    case = EvaluationCase(
        name="atlas deadline",
        category="exact",
        query="When is the Atlas deadline?",
        similarity_threshold=0.7,
        limit=3,
        candidates=[
            RerankCandidate("note:1", "note", 1, "Atlas", "Deadline Friday", 0.84),
            RerankCandidate("note:2", "note", 2, "Atlas meals", "Dinner Friday", 0.83),
        ],
        relevant_source_keys={"note:1"},
        cited_source_keys={"note:1"},
        exposed_source_keys={"note:1"},
    )

    result = evaluate_case(case)

    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.reciprocal_rank == 1.0
    assert result.citation_validity == 1.0
    assert result.uncited_reference_rate == 0.0


def test_evaluation_detects_invalid_citations_and_uncited_references() -> None:
    case = EvaluationCase(
        name="invalid references",
        category="grounding",
        query="Atlas",
        similarity_threshold=0.7,
        limit=2,
        candidates=[RerankCandidate("note:1", "note", 1, "Atlas", "Atlas", 0.84)],
        relevant_source_keys={"note:1"},
        cited_source_keys={"note:99"},
        exposed_source_keys={"note:1"},
    )

    result = evaluate_case(case)

    assert result.citation_validity == 0.0
    assert result.uncited_reference_rate == 1.0


def test_checked_in_evaluation_dataset_is_valid() -> None:
    path = Path(__file__).parents[1] / "evals" / "rag_cases.json"

    cases = load_evaluation_cases(path)

    assert {case.category for case in cases} == {
        "casual",
        "exact",
        "exact-name-rescue",
        "follow-up",
        "grounded-follow-up",
        "irrelevant",
        "irrelevant-lexical",
        "overview",
        "semantic",
    }
    results = [evaluate_case(case) for case in cases]
    assert average_metric(results, "precision") == 1.0
    assert average_metric(results, "recall") == 1.0


def test_duplicate_candidate_keys_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(
        """
        [{
          "name": "duplicate",
          "category": "exact",
          "query": "Atlas",
          "similarity_threshold": 0.7,
          "limit": 3,
          "candidates": [
            {"source_key": "note:1", "source_type": "note", "source_id": 1, "title": "A", "content": "A", "vector_score": 0.8},
            {"source_key": "note:1", "source_type": "note", "source_id": 1, "title": "A", "content": "A", "vector_score": 0.8}
          ],
          "relevant_source_keys": ["note:1"],
          "cited_source_keys": ["note:1"],
          "exposed_source_keys": ["note:1"]
        }]
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate candidate source_key"):
        load_evaluation_cases(path)
