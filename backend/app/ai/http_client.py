"""
HTTP client pooling for AI services.

This module provides singleton HTTP clients with connection pooling
to avoid connection overhead on every request.
"""
from __future__ import annotations

import httpx

# Singleton clients with connection pooling
_llm_client: httpx.AsyncClient | None = None
_embedding_client: httpx.AsyncClient | None = None


async def get_llm_client(timeout: float = 180.0) -> httpx.AsyncClient:
    """
    Get or create the singleton LLM HTTP client with connection pooling.

    Args:
        timeout: Request timeout in seconds (default 180s for long LLM responses)

    Returns:
        AsyncClient instance with connection pooling
    """
    global _llm_client
    if _llm_client is None or _llm_client.is_closed:
        _llm_client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(
                max_connections=10,
                max_keepalive_connections=5,
                keepalive_expiry=30.0,
            ),
        )
    return _llm_client


async def get_embedding_client(timeout: float = 120.0) -> httpx.AsyncClient:
    """
    Get or create the singleton embedding HTTP client with connection pooling.

    Args:
        timeout: Request timeout in seconds (default 120s for batch embeddings)

    Returns:
        AsyncClient instance with connection pooling
    """
    global _embedding_client
    if _embedding_client is None or _embedding_client.is_closed:
        _embedding_client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(
                max_connections=10,
                max_keepalive_connections=5,
                keepalive_expiry=30.0,
            ),
        )
    return _embedding_client


async def close_clients() -> None:
    """
    Close all singleton HTTP clients.
    Should be called during application shutdown.
    """
    global _llm_client, _embedding_client

    if _llm_client and not _llm_client.is_closed:
        await _llm_client.aclose()
        _llm_client = None

    if _embedding_client and not _embedding_client.is_closed:
        await _embedding_client.aclose()
        _embedding_client = None
