"""
Test endpoints for timeout verification.
These endpoints simulate slow operations and large uploads for testing timeout behavior.
"""

import asyncio
import time
from typing import Any

from fastapi import APIRouter, File, Query, UploadFile

router = APIRouter(prefix="/test", tags=["test"])


@router.get("/slow")
async def slow_endpoint(delay_seconds: int = Query(5, ge=1, le=300)) -> dict[str, Any]:
    """
    Slow endpoint that delays response by specified seconds.
    Used to test timeout configuration.

    - **delay_seconds**: Number of seconds to delay (1-300, default 5)

    Returns:
        Dictionary with elapsed time and request_id
    """
    start_time = time.time()
    await asyncio.sleep(delay_seconds)
    elapsed = time.time() - start_time

    return {
        "status": "success",
        "message": f"Response delayed by {elapsed:.2f} seconds",
        "delay_requested": delay_seconds,
        "delay_actual": elapsed,
    }


@router.post("/upload-large")
async def upload_large_file(file: UploadFile = File(...)) -> dict[str, Any]:
    """
    Endpoint to test large file upload timeout behavior.
    Accepts any file and returns upload statistics.

    Used to verify that file uploads don't timeout unexpectedly
    during normal operation.

    - **file**: File to upload

    Returns:
        Upload statistics including filename, size, and processing time
    """
    start_time = time.time()

    # Read file content
    contents = await file.read()
    file_size_mb = len(contents) / (1024 * 1024)

    elapsed = time.time() - start_time

    return {
        "status": "success",
        "filename": file.filename,
        "content_type": file.content_type,
        "size_bytes": len(contents),
        "size_mb": f"{file_size_mb:.2f}",
        "upload_time_seconds": f"{elapsed:.2f}",
    }


@router.post("/rag-slow")
async def rag_slow_query(
    query: str = Query(...), delay_seconds: int = Query(10, ge=1, le=300)
) -> dict[str, Any]:
    """
    Simulate a slow RAG query for timeout testing.
    In production, RAG queries can take significant time due to:
    - Embedding generation
    - Vector search on large document sets
    - LLM generation

    Used to verify that long-running RAG operations complete within
    configured timeout window or properly fail with timeout error.

    - **query**: The search query
    - **delay_seconds**: Simulated RAG processing time (1-300, default 10)

    Returns:
        Simulated RAG response with query, delay, and mock documents
    """
    start_time = time.time()

    # Simulate RAG processing: embedding + search + generation
    await asyncio.sleep(delay_seconds)

    elapsed = time.time() - start_time

    return {
        "status": "success",
        "query": query,
        "delay_requested": delay_seconds,
        "delay_actual": f"{elapsed:.2f}",
        "documents": [
            {
                "id": 1,
                "title": "Sample Document 1",
                "relevance_score": 0.95,
                "excerpt": f"Response to query '{query}' after {delay_seconds}s processing",
            },
        ],
        "answer": f"Answer to '{query}' after simulated RAG processing",
    }
