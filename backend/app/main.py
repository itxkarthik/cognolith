from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.config import settings
from app.core.database import create_db_and_tables
from app.core.middleware import SecurityHeadersMiddleware, RequestIDMiddleware
from app.api.main import api_router

# Rate Limiter
from app.core.rate_limit import limiter

# FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.VERSION,
    debug=settings.DEBUG
)

# Attach limiter state so slowapi can access it inside route handlers
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 1. Request ID — runs first so all downstream middleware/routes have access
app.add_middleware(RequestIDMiddleware)

# 2. Security Headers — added to every response
app.add_middleware(SecurityHeadersMiddleware)

# 3. CORS — locked down to specific methods and headers
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.all_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
)

# Startup
@app.on_event("startup")
def on_startup():
    create_db_and_tables()

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
    return {"status": "healthy"}


# API router
app.include_router(api_router, prefix=settings.API_V1_STR)
