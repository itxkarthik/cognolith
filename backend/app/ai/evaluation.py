from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.ai.reranking import RerankCandidate, rerank_candidates


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    name: str
    category: str
    query: str
    similarity_threshold: float
    limit: int
    candidates: list[RerankCandidate]
    relevant_source_keys: set[str]
    cited_source_keys: set[str]
    exposed_source_keys: set[str]


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    name: str
    category: str
    retrieved_source_keys: list[str]
    precision: float
    recall: float
    reciprocal_rank: float
    citation_validity: float
    uncited_reference_rate: float


def evaluate_case(case: EvaluationCase) -> EvaluationResult:
    ranked = rerank_candidates(
        query=case.query,
        candidates=case.candidates,
        similarity_threshold=case.similarity_threshold,
        limit=case.limit,
    )
    retrieved = [candidate.source_key for candidate in ranked]
    retrieved_set = set(retrieved)
    relevant_retrieved = retrieved_set.intersection(case.relevant_source_keys)

    precision = (
        len(relevant_retrieved) / len(retrieved)
        if retrieved
        else float(not case.relevant_source_keys)
    )
    recall = (
        len(relevant_retrieved) / len(case.relevant_source_keys)
        if case.relevant_source_keys
        else 1.0
    )
    reciprocal_rank = 0.0
    for rank, source_key in enumerate(retrieved, start=1):
        if source_key in case.relevant_source_keys:
            reciprocal_rank = 1.0 / rank
            break
    if not case.relevant_source_keys:
        reciprocal_rank = 1.0

    citation_validity = (
        len(case.cited_source_keys.intersection(retrieved_set)) / len(case.cited_source_keys)
        if case.cited_source_keys
        else 1.0
    )
    uncited_reference_rate = (
        len(case.exposed_source_keys.difference(case.cited_source_keys))
        / len(case.exposed_source_keys)
        if case.exposed_source_keys
        else 0.0
    )
    return EvaluationResult(
        name=case.name,
        category=case.category,
        retrieved_source_keys=retrieved,
        precision=precision,
        recall=recall,
        reciprocal_rank=reciprocal_rank,
        citation_validity=citation_validity,
        uncited_reference_rate=uncited_reference_rate,
    )


def load_evaluation_cases(path: Path) -> list[EvaluationCase]:
    raw_cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_cases, list):
        raise ValueError("evaluation dataset must contain a list")

    cases: list[EvaluationCase] = []
    for raw_case in raw_cases:
        raw_candidates = raw_case["candidates"]
        candidates = [RerankCandidate(**candidate) for candidate in raw_candidates]
        source_keys = [candidate.source_key for candidate in candidates]
        if len(source_keys) != len(set(source_keys)):
            raise ValueError(f"{raw_case['name']}: duplicate candidate source_key")
        cases.append(
            EvaluationCase(
                name=raw_case["name"],
                category=raw_case["category"],
                query=raw_case["query"],
                similarity_threshold=float(raw_case["similarity_threshold"]),
                limit=int(raw_case["limit"]),
                candidates=candidates,
                relevant_source_keys=set(raw_case["relevant_source_keys"]),
                cited_source_keys=set(raw_case["cited_source_keys"]),
                exposed_source_keys=set(raw_case["exposed_source_keys"]),
            )
        )
    return cases


def average_metric(results: list[EvaluationResult], attribute: str) -> float:
    if not results:
        return 0.0
    return sum(float(getattr(result, attribute)) for result in results) / len(results)
