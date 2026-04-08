import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.config import settings
from app.core.database import create_db_and_tables_with_retry
from app.core.middleware import SecurityHeadersMiddleware, RequestIDMiddleware, MaxRequestBodySizeMiddleware
from app.api.main import api_router

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

# 1. Request ID — runs first so all downstream middleware/routes have access
app.add_middleware(RequestIDMiddleware)

# 2. Security Headers — added to every response
app.add_middleware(SecurityHeadersMiddleware)

# 3. Max Request Body Size — reject oversized payloads early
app.add_middleware(MaxRequestBodySizeMiddleware)

# 4. CORS — locked down to specific methods and headers
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
        "docs": "/docs"
    }


@app.get("/health")
def health_check():
    """
    Simple health check endpoint.
    Returns 200 OK if the service is running.
    """
    return {"status": "healthy"}


# API router
app.include_router(api_router, prefix=settings.API_V1_STR)
