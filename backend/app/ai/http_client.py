"""
HTTP client factories for AI services.

RAG calls can run on short-lived event loops, so clients must not be shared
globally across requests. Each client still pools connections for its own call.
"""

from __future__ import annotations

import httpx


def _create_client(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout),
        limits=httpx.Limits(
            max_connections=10,
            max_keepalive_connections=5,
            keepalive_expiry=30.0,
        ),
    )


def create_llm_client(timeout: float = 180.0) -> httpx.AsyncClient:
    return _create_client(timeout)


def create_embedding_client(timeout: float = 120.0) -> httpx.AsyncClient:
    return _create_client(timeout)
