"""Substring search for list endpoints."""

from typing import Any

from sqlalchemy import ColumnElement, func


def contains_ignoring_case(column: Any, term: str) -> ColumnElement[bool]:
    """
    Case-insensitive match of `term` as literal text: `%` and `_` typed by the user
    match themselves instead of acting as wildcards.

    Rendered as `lower(column) LIKE ...` so pg_trgm indexes on `lower(column)` apply.
    """
    return func.lower(column).contains(term.lower(), autoescape=True)
