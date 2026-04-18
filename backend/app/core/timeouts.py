"""
Endpoint-specific timeout configurations and middleware.
"""


# Timeout values in seconds for different endpoint categories
TIMEOUT_CONFIG = {
    # File upload endpoints - allow longer processing time
    "file_upload": 120.0,  # 120 seconds
    # RAG and AI operations - semantic search and generation takes time
    "rag_query": 60.0,  # 60 seconds
    "chat": 60.0,  # 60 seconds
    "search": 60.0,  # 60 seconds
    "knowledge_graph": 60.0,  # 60 seconds
    # Regular API operations - standard timeout
    "default": 15.0,  # 15 seconds
    # Health checks - very fast
    "health_check": 5.0,  # 5 seconds
}


def get_timeout_for_endpoint(path: str, method: str = "GET") -> float:
    """
    Get the appropriate timeout value for an endpoint.

    Args:
        path: The request path (e.g., "/api/v1/documents/upload")
        method: The HTTP method (GET, POST, etc.)

    Returns:
        Timeout value in seconds
    """
    # Normalize path
    path = path.rstrip("/").lower()

    # Health check endpoints
    if path.endswith("/health") or path == "/health":
        return TIMEOUT_CONFIG["health_check"]

    # File upload endpoints
    if "documents/upload" in path or "upload" in path:
        return TIMEOUT_CONFIG["file_upload"]

    # RAG and search endpoints
    if any(keyword in path for keyword in ["rag", "search", "knowledge-graph"]):
        return TIMEOUT_CONFIG["rag_query"]

    # Chat endpoints
    if "chat" in path:
        return TIMEOUT_CONFIG["chat"]

    # Default timeout for all other endpoints
    return TIMEOUT_CONFIG["default"]
