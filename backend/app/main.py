import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.main import api_router
from app.api.routes.test import router as test_router
from app.core.config import settings
from app.core.csrf import CSRFMiddleware
from app.core.database import create_db_and_tables_with_retry, test_db_connection
from app.core.exceptions import AppException, global_exception_handler
from app.core.middleware import (
    MaxRequestBodySizeMiddleware,
    RequestIDMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)

# Rate Limiter
from app.core.rate_limit import limiter

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """
    FastAPI lifespan context manager for startup and shutdown events.
    Handles database initialization with retry logic on startup.
    """
    # Startup
    try:
        logger.info("Starting application...")

        # Initialize database with retry logic
        # This ensures the app can handle cases where the database
        # is not immediately available (e.g., in Docker Compose)
        await create_db_and_tables_with_retry(
            max_retries=5,
            initial_delay=1,
        )

        logger.info("✓ Application startup complete")
    except Exception as e:
        logger.error(f"✗ Application startup failed: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down application...")


# FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# Attach limiter state so slowapi can access it inside route handlers
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Register global exception handler for all exceptions
# This must be registered AFTER specific handlers (like RateLimitExceeded)
app.add_exception_handler(AppException, global_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

# 1. Request ID — runs first so all downstream middleware/routes have access
app.add_middleware(RequestIDMiddleware)

# 2. Request Logging — logs all requests/responses with structured JSON format
app.add_middleware(RequestLoggingMiddleware)

# 3. CSRF Protection — validates CSRF tokens on state-changing requests
app.add_middleware(CSRFMiddleware)

# 4. Security Headers — added to every response
app.add_middleware(SecurityHeadersMiddleware)

# 5. Max Request Body Size — reject oversized payloads early
app.add_middleware(MaxRequestBodySizeMiddleware)

# 6. CORS — locked down to specific methods and headers
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.all_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "X-Request-ID",
        settings.CSRF_HEADER_NAME,
        "X-Requested-With",
    ],
)


# Public endpoints
@app.get("/")
def read_root():
    return {
        "message": "Welcome to Personal Knowledge Assistant API",
        "version": settings.VERSION,
        "docs": "/docs",
    }


@app.get("/health")
def health_check():
    """
    Backward-compatible health endpoint.
    """
    return {"status": "healthy", "check": "liveness"}


@app.get("/health/live")
def health_live():
    """Liveness probe: process is running and can serve requests."""
    return {"status": "alive"}


async def _check_ollama_connection() -> bool:
    ollama_tags_url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(ollama_tags_url)
            return response.status_code == 200
    except Exception as exc:
        logger.warning("Ollama readiness check failed: %s", exc)
        return False


@app.get("/health/ready")
async def health_ready():
    """Readiness probe: verifies dependencies required to serve traffic."""
    db_ready = await test_db_connection()
    ollama_ready = await _check_ollama_connection()
    require_ollama = settings.ENVIRONMENT == "production"
    ready = db_ready and (ollama_ready or not require_ollama)

    payload = {
        "status": "ready" if ready else "not_ready",
        "require_ollama": require_ollama,
        "dependencies": {
            "database": "up" if db_ready else "down",
            "ollama": "up" if ollama_ready else "down",
        },
    }
    if ready:
        return payload
    return JSONResponse(status_code=503, content=payload)


# API router
app.include_router(api_router, prefix=settings.API_V1_STR)

# Test routes (for timeout verification and testing)
app.include_router(test_router, prefix=settings.API_V1_STR)
