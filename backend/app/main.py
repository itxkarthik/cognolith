from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import create_db_and_tables
from app.api.main import api_router

# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.VERSION,
    debug=settings.DEBUG
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.all_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
)

# Create database tables on startup
@app.on_event("startup")
def on_startup():
    create_db_and_tables()

# Root endpoint
@app.get("/")
def read_root():
    return {
        "message": "Welcome to Personal Knowledge Assistant API",
        "version": settings.VERSION,
        "docs": "/docs"
    }

# Health check endpoint
@app.get("/health")
def health_check():
    return {"status": "healthy"}

# Include API router with versioned prefix
app.include_router(api_router, prefix=settings.API_V1_STR)
