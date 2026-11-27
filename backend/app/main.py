import logging
from contextlib import asynccontextmanager
from typing import Any, cast

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlmodel import Session

from app.ai.embedding_validation import validate_embedding_setup
from app.api.main import api_router
from app.api.routes.test import router as test_router
from app.core.cache_middleware import ETagAndCacheMiddleware
from app.core.config import settings
from app.core.csrf import CSRFMiddleware
from app.core.database import engine, test_db_connection
from app.core.exceptions import AppError, global_exception_handler
from app.core.middleware import (
    MaxRequestBodySizeMiddleware,
    RateLimitMiddleware,
    RequestIDMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.rate_limit import limiter
from app.services.backup_scheduler import BackupScheduler
from app.services.chat_generation import fail_interrupted_generations
from app.services.document_processing import document_processor
from app.services.maintenance_scheduler import MaintenanceScheduler
from app.services.workspace_indexer import workspace_indexer

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """
    FastAPI lifespan context manager for startup and shutdown events.
    Handles database initialization with retry logic on startup.
    """
    backup_scheduler = BackupScheduler()
    maintenance_scheduler = MaintenanceScheduler()

    # Startup
    try:
        logger.info("Starting application...")

        if not await test_db_connection():
            raise ConnectionError("Database connection test failed")

        await validate_embedding_setup()

        # Replies cut off by the last shutdown or crash become retryable
        with Session(engine) as session:
            interrupted = fail_interrupted_generations(session)
        if interrupted:
            logger.info("Marked %s interrupted chat repl(ies) as failed", interrupted)

        # Uploads interrupted by the last shutdown or crash are processed again
        resumed = document_processor.resume_interrupted()
        if resumed:
            logger.info("Resumed processing of %s interrupted document(s)", resumed)

        await backup_scheduler.start()
        await maintenance_scheduler.start()
        # Embeds new and changed content; chat and search only read vectors
        await workspace_indexer.start()

        logger.info("✓ Application startup complete")
    except Exception as e:
        logger.error(f"✗ Application startup failed: {e}")
        raise

    try:
        yield
    finally:
        await workspace_indexer.stop()
        await maintenance_scheduler.stop()
        await backup_scheduler.stop()
        await document_processor.shutdown()
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
app.add_exception_handler(RateLimitExceeded, cast(Any, _rate_limit_exceeded_handler))

# Register global exception handler for all exceptions
# This must be registered AFTER specific handlers (like RateLimitExceeded)
app.add_exception_handler(AppError, global_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

# Middleware, outermost first: CORS > request id > logging > security headers >
# body size > rate limit > CSRF > cache/ETag > routes. Each add_middleware call wraps
# the ones added before it, so they are added innermost first.
# CORS is outermost so even a refused request (403, 413, 429) is readable by the
# browser; the request id comes next so every log line and error carries it.
app.add_middleware(ETagAndCacheMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(MaxRequestBodySizeMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RequestIDMiddleware)
# Outermost; locked down to specific methods and headers
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
        "message": "Welcome to the Cognolith API",
        "version": settings.VERSION,
        "docs": "/docs",
    }


@app.get("/health")
@limiter.exempt
def health_check():
    """
    Backward-compatible health endpoint.
    """
    return {"status": "healthy", "check": "liveness"}


@app.get("/health/live")
@limiter.exempt
def health_live():
    """Liveness probe: process is running and can serve requests."""
    return {"status": "alive"}


async def _check_ollama_connection() -> tuple[bool, list[str]]:
    ollama_tags_url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(ollama_tags_url)
            response.raise_for_status()
            payload = response.json()
            installed_models = {
                str(model.get("name", "")).split(":", maxsplit=1)[0]
                for model in payload.get("models", [])
                if isinstance(model, dict)
            }
            required_models = {
                settings.OLLAMA_CHAT_MODEL.split(":", maxsplit=1)[0],
                settings.OLLAMA_EMBEDDING_MODEL.split(":", maxsplit=1)[0],
            }
            missing_models = sorted(required_models - installed_models)
            return not missing_models, missing_models
    except Exception as exc:
        logger.warning("Ollama readiness check failed: %s", exc)
        return False, [settings.OLLAMA_CHAT_MODEL, settings.OLLAMA_EMBEDDING_MODEL]


@app.get("/health/ready")
@limiter.exempt
async def health_ready():
    """Readiness probe: verifies dependencies required to serve traffic."""
    db_ready = await test_db_connection()
    ollama_ready, missing_models = await _check_ollama_connection()
    require_ollama = settings.ENVIRONMENT == "production"
    ready = db_ready and (ollama_ready or not require_ollama)

    payload = {
        "status": "ready" if ready else "not_ready",
        "require_ollama": require_ollama,
        "dependencies": {
            "database": "up" if db_ready else "down",
            "ollama": "up" if ollama_ready else "down",
        },
        "ai": {
            "chat_model": settings.OLLAMA_CHAT_MODEL,
            "embedding_model": settings.OLLAMA_EMBEDDING_MODEL,
            "missing_models": missing_models,
        },
    }
    if ready:
        return payload
    return JSONResponse(status_code=503, content=payload)


# API router
app.include_router(api_router, prefix=settings.API_V1_STR)

# Test routes (for timeout verification) are unauthenticated, so only mount them locally
if settings.ENVIRONMENT == "local":
    app.include_router(test_router, prefix=settings.API_V1_STR)
