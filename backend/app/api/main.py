from fastapi import APIRouter
from app.api.routes import auth, documents, user

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(user.router)
api_router.include_router(documents.router)
# Future routes will be added here as they are implemented:
# api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
# api_router.include_router(notes.router, prefix="/notes", tags=["notes"])
# api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
# api_router.include_router(search.router, prefix="/search", tags=["search"])