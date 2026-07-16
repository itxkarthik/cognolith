from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "from",
    "i",
    "in",
    "is",
    "me",
    "my",
    "of",
    "on",
    "the",
    "to",
    "what",
    "when",
    "where",
    "which",
    "who",
    "with",
}
_RETRIEVAL_INTENT_WORDS = {
    "about",
    "describe",
    "detail",
    "details",
    "document",
    "explain",
    "give",
    "more",
    "note",
    "please",
    "project",
    "resume",
    "show",
    "tell",
}


@dataclass(frozen=True, slots=True)
class LexicalQuery:
    phrase: str
    compact_phrase: str
    terms: tuple[str, ...]


def build_lexical_query(query: str) -> LexicalQuery:
    tokens = _TOKEN_PATTERN.findall(query.casefold())
    terms = tuple(
        token
        for token in tokens
        if token not in _STOP_WORDS and token not in _RETRIEVAL_INTENT_WORDS
    )
    phrase = " ".join(terms)
    return LexicalQuery(
        phrase=phrase,
        compact_phrase="".join(terms),
        terms=terms,
    )


@dataclass(frozen=True, slots=True)
class RerankCandidate:
    source_key: str
    source_type: str
    source_id: int
    title: str
    content: str
    vector_score: float | None
    lexical_score: float = 0.0
    exact_match: bool = False
    prior_source: bool = False


@dataclass(frozen=True, slots=True)
class RerankedCandidate:
    source_key: str
    source_type: str
    source_id: int
    title: str
    content: str
    vector_score: float | None
    hybrid_score: float
    lexical_score: float
    exact_match: bool
    prior_source: bool
    match_type: str


def normalized_terms(value: str) -> set[str]:
    return {
        _normalize_term(token)
        for token in _TOKEN_PATTERN.findall(value.casefold())
        if token not in _STOP_WORDS
    }


def _normalize_term(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return f"{token[:-3]}y"
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _coverage(query_terms: set[str], value: str) -> float:
    if not query_terms:
        return 0.0
    return len(query_terms.intersection(normalized_terms(value))) / len(query_terms)


def _phrase_match(query: str, title: str, content: str) -> float:
    normalized_query = " ".join(_TOKEN_PATTERN.findall(query.casefold()))
    if len(normalized_query.split()) < 2:
        return 0.0
    searchable = " ".join(_TOKEN_PATTERN.findall(f"{title} {content}".casefold()))
    return 1.0 if normalized_query in searchable else 0.0


def rerank_candidates(
    *,
    query: str,
    candidates: Sequence[RerankCandidate],
    similarity_threshold: float,
    limit: int,
    hybrid_score_window: float = 0.10,
) -> list[RerankedCandidate]:
    if limit <= 0:
        return []

    query_terms = normalized_terms(query)
    ranked: list[RerankedCandidate] = []
    for candidate in candidates:
        vector_score = candidate.vector_score or 0.0
        content_coverage = _coverage(query_terms, candidate.content)
        phrase_match = _phrase_match(query, candidate.title, candidate.content)
        lexical_score = max(candidate.lexical_score, content_coverage, phrase_match)
        semantic_match = vector_score >= similarity_threshold
        lexical_match = candidate.exact_match or (lexical_score >= 0.60 and vector_score >= 0.50)
        if not semantic_match and not lexical_match:
            continue

        title_coverage = _coverage(query_terms, candidate.title)
        hybrid_score = (
            (vector_score * 0.55)
            + (lexical_score * 0.30)
            + (title_coverage * 0.10)
            + (float(candidate.prior_source) * 0.05)
        )
        match_type = (
            "hybrid"
            if lexical_score > 0 and candidate.vector_score is not None
            else "lexical" if lexical_score > 0 else "vector"
        )
        ranked.append(
            RerankedCandidate(
                source_key=candidate.source_key,
                source_type=candidate.source_type,
                source_id=candidate.source_id,
                title=candidate.title,
                content=candidate.content,
                vector_score=candidate.vector_score,
                hybrid_score=round(hybrid_score, 8),
                lexical_score=lexical_score,
                exact_match=candidate.exact_match,
                prior_source=candidate.prior_source,
                match_type=match_type,
            )
        )

    ranked.sort(key=lambda item: (-item.hybrid_score, item.source_key))
    if not ranked:
        return []

    minimum_score = ranked[0].hybrid_score - max(0.0, hybrid_score_window)
    return [item for item in ranked if item.hybrid_score >= minimum_score][:limit]
